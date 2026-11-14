## 개요

SAN 스토리지를 서버에 붙일 때 경로가 제대로 이중화되어 있는지 확인하고, LUN 을 추가·확장하는 절차다. 멀티패스가 깨진 채로 운영하다 HBA 나 스위치 한 쪽이 죽으면 그대로 장애로 이어진다.

## 배경

서버에서 스토리지까지 가는 길은 보통 두 갈래 이상이다. HBA 두 장, 패브릭 스위치 두 대, 스토리지 컨트롤러 두 개. 같은 LUN 이 여러 경로로 보이므로, OS 는 이것이 하나의 디스크임을 알아야 한다. 그 역할이 멀티패스(dm-multipath)다.

멀티패스가 설정되지 않으면 같은 LUN 이 `/dev/sdb`, `/dev/sdc` 처럼 따로 보인다. 이 상태에서 각각 마운트하면 데이터가 깨진다.

## 확인

```
# 경로 상태 — 경로 수와 active/enabled 확인
multipath -ll

# HBA 포트와 링크 상태
systool -c fc_host -v | grep -E "port_name|port_state"
cat /sys/class/fc_host/host*/port_state

# 디스크와 WWID 매핑
lsblk -o NAME,SIZE,WWN,MOUNTPOINT
```

`multipath -ll` 결과에서 봐야 할 것은 세 가지다. 경로 수가 설계와 같은지, 모든 경로가 `active ready` 인지, 정책(`service-time`, `round-robin`)이 스토리지 벤더 권장과 맞는지.

경로 하나가 `failed faulty` 로 보이면 그 쪽 HBA·케이블·스위치 포트 중 하나가 문제다. 서비스는 살아 있지만 이중화는 깨진 상태다.

## LUN 추가

1. 스토리지에서 LUN 을 만들고 해당 서버의 WWPN 에 매핑한다.
2. 서버에서 다시 읽는다.

```
for h in /sys/class/scsi_host/host*/scan; do echo "- - -" > $h; done
multipath -r
multipath -ll | head
```

3. 새 `/dev/mapper/mpathX` 를 확인하고 LVM 으로 잡는다.

```
pvcreate /dev/mapper/mpathc
vgextend vg_data /dev/mapper/mpathc
```

## LUN 확장

기존 LUN 크기를 스토리지에서 늘린 경우다.

```
# 각 경로에 다시 읽히기
for d in $(multipath -l mpathb | grep -o 'sd[a-z]*'); do
  echo 1 > /sys/block/$d/device/rescan
done

multipathd -k'resize map mpathb'
pvresize /dev/mapper/mpathb
vgs
```

## 운영 시 주의

- **`/dev/sdX` 를 직접 쓰지 않는다.** 재부팅하면 순서가 바뀐다. 항상 `/dev/mapper/mpathX` 나 WWID, UUID 로 지정한다. `/etc/fstab` 도 마찬가지다.
- 경로가 하나로 줄어든 상태를 모르고 지나가는 일이 흔하다. `multipath -ll` 결과의 경로 수를 모니터링 항목에 넣는다.
- 멀티패스 설정(`/etc/multipath.conf`)은 스토리지 벤더 권장값을 따른다. 기본값으로 두면 장애 전환 시간이 길어지는 경우가 있다.
- LUN 을 뺄 때는 LVM 에서 먼저 제거(`vgreduce`, `pvremove`)하고, 멀티패스 맵을 지운 뒤, 스토리지에서 매핑을 푼다. 순서를 뒤집으면 커널에 유령 장치가 남는다.

## 실무 권장

- 서버별로 **WWPN, LUN ID, 용도, 크기**를 표로 관리한다. 장애 때 이 표가 없으면 어느 LUN 이 무엇인지 찾는 데만 시간이 간다.
- 신규 구성 후에는 한쪽 경로를 일부러 내려 보고 전환을 확인한다. 평상시에 해 두지 않으면 진짜 장애 때 전환이 되는지 알 수 없다.
- 펌웨어와 드라이버 조합은 벤더 호환성 목록을 확인한다. 멀티패스 문제의 상당수가 조합 불일치에서 나온다.

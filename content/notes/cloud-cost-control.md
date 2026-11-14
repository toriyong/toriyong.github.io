## 개요

클라우드 비용이 왜 늘었는지 찾고 줄이는 방법이다. 비용은 기술 문제라기보다 **무엇이 켜져 있는지 아무도 모르는** 문제인 경우가 많다.

## 배경

청구서가 갑자기 늘었을 때 원인은 대체로 정해져 있다.

| 원인 | 특징 |
| --- | --- |
| 꺼야 할 것이 켜져 있음 | 테스트 VM, 임시 환경 |
| 떼어낸 리소스가 남아 있음 | 미연결 디스크·공인 IP, 스냅샷 |
| 데이터 전송 요금 | 리전 간, 인터넷 아웃바운드 |
| 로그·백업 보관 | 조용히 계속 쌓임 |
| 과대 산정 | 쓰지도 않는 크기로 띄움 |

금액이 큰 순서는 보통 컴퓨트 → 스토리지 → 전송이다. 그런데 **갑작스러운 증가**는 전송 요금인 경우가 많다. 잘못 설정된 복제나 백업이 리전을 넘어가면 금방 불어난다.

## 찾기

```bash
# Azure — 서비스별 비용 (지난달)
az consumption usage list --start-date 2026-10-01 --end-date 2026-10-31 \
  --query "[].{svc:meterDetails.meterCategory, cost:pretaxCost}" -o tsv |
  awk -F'\t' '{a[$1]+=$2} END {for (k in a) printf "%-35s %10.2f\n", k, a[k]}' | sort -k2 -rn

# 미연결 디스크 — 붙어 있지 않은데 과금된다
az disk list --query "[?diskState=='Unattached'].{name:name,gb:diskSizeGb,rg:resourceGroup}" -o table

# 미할당 공인 IP
az network public-ip list --query "[?ipConfiguration==null].{name:name,rg:resourceGroup}" -o table
```

```bash
# OCI — 부팅 볼륨이 떨어져 있는 것
oci bv boot-volume list --compartment-id <ocid> --all \
  --query "data[?\"lifecycle-state\"=='AVAILABLE'].{name:\"display-name\",gb:\"size-in-gbs\"}" -o table

# 중지된 인스턴스 — 중지해도 블록 볼륨은 계속 과금된다
oci compute instance list --compartment-id <ocid> --all \
  --query "data[?\"lifecycle-state\"=='STOPPED'].{name:\"display-name\",shape:shape}" -o table
```

**인스턴스를 중지해도 디스크 요금은 계속 나간다.** 자주 놓치는 지점이다.

## 줄이기

효과가 큰 순서다.

**1. 안 쓰는 것을 끈다.** 개발·테스트 환경을 업무 시간에만 켠다. 평일 9시간만 쓰면 비용이 1/4 수준이 된다. 자동화로 거는 게 맞다.

```bash
# Azure Automation 이나 스케줄로
az vm deallocate --ids $(az vm list -g rg-dev --query "[].id" -o tsv)
```

`stop` 이 아니라 `deallocate` 여야 과금이 멈춘다. 이것도 자주 틀린다.

**2. 크기를 맞춘다.** CPU 사용률이 계속 10% 밑이면 한 단계 줄인다. 다만 메모리와 네트워크 성능이 같이 줄어드니 확인하고 한다.

**3. 약정 할인을 쓴다.** 1년 이상 유지가 확실한 워크로드는 예약 인스턴스(Azure Reserved, OCI 연간 약정)로 돌린다. 30~60% 절감된다. **확실한 것만** 건다. 중간에 바꾸기 어렵다.

**4. 스토리지 계층을 나눈다.** 접근이 드문 데이터는 저빈도·아카이브 계층으로 내린다. 수명 주기 규칙으로 자동화한다. 다만 아카이브는 꺼낼 때 시간과 비용이 든다.

**5. 로그 보관 기간을 정한다.** Log Analytics 나 OCI Logging 의 보관 기간이 기본값으로 길게 잡혀 조용히 쌓이는 경우가 흔하다.

## 구조적으로 막기

**태그를 강제한다.** 최소 세 개 — `환경`, `담당`, `서비스`. 없으면 생성을 막는 정책을 건다.

```bash
# Azure Policy 로 태그 필수화 (예시)
az policy assignment create --name require-tags \
  --policy <정책정의ID> --scope /subscriptions/<sub-id>
```

태그가 없으면 "이 VM 은 누구 건가"를 알 수 없어 아무도 못 지운다. 비용 문제의 절반이 여기서 온다.

**예산 경보를 건다.** 월 예산의 50%·80%·100% 에서 알림이 오게 한다. 청구서를 받고 나서 아는 것과 중간에 아는 것은 다르다.

## 운영 시 주의

- 비용 절감으로 **백업과 로그를 먼저 줄이지 않는다.** 사고 났을 때 제일 비싸게 치른다.
- 리소스를 지우기 전에 태그와 의존 관계를 확인한다. 미연결 디스크처럼 보여도 복구용으로 남겨둔 것일 수 있다.
- 리전 간 전송이 걸린 구성을 찾아본다. 백업 대상이 다른 리전이면 매달 전송 요금이 나간다.
- 예약 인스턴스는 **구독·리전·크기 계열**이 맞아야 적용된다. 샀는데 적용이 안 되는 경우가 있으니 적용률을 확인한다.

## 실무 권장

- 월 1회 **상위 10개 비용 항목**을 보는 루틴을 만든다. 전부 보려 하면 아무도 안 본다.
- 전월 대비 20% 이상 늘어난 항목만 추적한다. 증가분에 원인이 있다.
- 개발 환경은 만들 때부터 **만료일**을 태그에 넣는다. 만료된 것을 월 1회 걷어낸다.

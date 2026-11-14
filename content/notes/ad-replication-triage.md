## 개요

Active Directory 복제가 멈췄을 때 진단하는 순서다. 복제 문제는 로그인 실패, 그룹 정책 미적용, 비밀번호 변경 미반영 같은 형태로 먼저 드러난다.

## 배경

도메인 컨트롤러(DC)는 서로 변경 사항을 주고받는다. 이 복제가 끊기면 **DC 마다 다른 상태**가 된다. A 에서 만든 계정이 B 에서는 없고, B 에서 바꾼 비밀번호가 A 에서는 안 먹는다.

복제가 멈추는 원인은 대체로 넷이다.

| 원인 | 전형적 증상 |
| --- | --- |
| 네트워크·방화벽 | 특정 사이트 간만 실패 |
| DNS | DC 가 상대를 못 찾음 |
| 시간 차이 | Kerberos 인증 실패 (기본 5분 초과) |
| 토움스톤 기간 초과 | 오래 꺼져 있던 DC 가 복귀 |

마지막 것이 가장 위험하다. 복제 중단 상태로 기본 180일이 지난 DC 는 그냥 켜면 안 된다. 지워진 객체가 되살아난다.

## 진단

```powershell
# 복제 상태 요약 — 여기부터 본다
repadmin /replsummary

# DC 별 상세
repadmin /showrepl * /csv > C:\repl.csv

# 전반 점검
dcdiag /v /c /e

# 복제 큐
repadmin /queue
```

`repadmin /replsummary` 의 `largest delta` 가 몇 시간을 넘으면 문제다. `fails/total` 이 0 이 아닌 DC 를 먼저 본다.

### DNS

```powershell
dcdiag /test:dns /v /e
nltest /dsgetdc:<도메인> 
ipconfig /all          # DC 의 DNS 서버가 자기 자신만 가리키면 안 된다
```

DC 의 기본 DNS 는 **다른 DC**, 보조로 자기 자신(127.0.0.1)을 두는 구성이 권장된다. 자기 자신만 보게 두면 부팅 시 순환 참조가 생긴다.

### 시간

```powershell
w32tm /query /status
w32tm /monitor
```

Kerberos 는 기본적으로 5분 이상 차이나면 인증을 거부한다. PDC 에뮬레이터 역할을 가진 DC 가 외부 시간원을 보고, 나머지는 도메인 계층을 따르는 게 표준이다.

```powershell
netdom query fsmo           # 역할 보유 DC 확인
```

### 포트

```powershell
Test-NetConnection <상대DC> -Port 389     # LDAP
Test-NetConnection <상대DC> -Port 445     # SMB
Test-NetConnection <상대DC> -Port 88      # Kerberos
```

RPC 동적 포트(49152–65535)가 막혀 있으면 복제가 안 된다. 방화벽 담당과 협의가 필요한 전형적 항목이다. 고정하려면 레지스트리로 범위를 좁힐 수 있지만, 변경 후 재기동이 필요하다.

## 조치

연결은 되는데 복제가 안 밀렸다면 강제로 돌려본다.

```powershell
repadmin /syncall /AdeP
```

에러 코드로 방향이 갈린다.

| 코드 | 의미 | 방향 |
| --- | --- | --- |
| 8524 | DNS 조회 실패 | DNS 부터 |
| 1722 | RPC 서버 사용 불가 | 네트워크·방화벽 |
| 8606 / 8451 | 객체·DB 불일치 | 신중히, MS 문서 확인 |
| 2146893022 | 시간·SPN 문제 | 시간 동기화 확인 |

## 운영 시 주의

- **토움스톤 기간을 넘긴 DC 는 네트워크에 붙이지 않는다.** 정리(metadata cleanup) 후 재구축이 원칙이다. 그냥 켜면 삭제된 객체가 되살아나 전체에 퍼진다.
- 복제 문제 조치 중에는 대량 계정 작업(일괄 생성·삭제)을 멈춘다. 불일치가 커진다.
- `dcdiag` 경고를 전부 고치려 들지 않는다. 환경에 따라 정상인 항목이 있다. 복제·DNS·시간 세 가지를 먼저 본다.
- FSMO 역할 이전은 되돌리기 어렵다. 강제 이전(seize)은 원래 보유 DC 를 다시 안 쓸 때만 한다.

## 실무 권장

- `repadmin /replsummary` 를 일 1회 자동 실행해 결과를 메일이나 채널로 받는다. 복제는 조용히 끊기고, 증상은 한참 뒤에 나타난다.
- 사이트·서브넷 구성을 실제 네트워크와 맞춰 둔다. 안 맞으면 클라이언트가 먼 DC 로 붙어 로그인이 느려진다.
- DC 백업은 시스템 상태(System State)를 포함해야 복구가 된다. 파일 백업만으로는 AD 가 안 돌아온다.

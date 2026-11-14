## 개요

서버에 누가 어떻게 접근하는지를 통제하는 구성이다. 접근 경로를 줄이고, 남은 경로는 전부 기록으로 남기는 것이 목표다.

## 배경

관리자 접근은 침해 사고에서 가장 많이 쓰이는 길이다. 열려 있는 관리 포트, 공용으로 쓰는 계정, 어디서든 들어올 수 있는 VPN 하나가 그대로 사고 경로가 된다.

통제 논리는 세 층으로 나눠 보면 정리된다.

| 층 | 질문 | 수단 |
| --- | --- | --- |
| 망 | 어디서 들어올 수 있나 | 방화벽, 보안그룹/NSG, 점프 서버 |
| 인증 | 누구인지 어떻게 확인하나 | 계정 분리, 키 기반 인증, MFA |
| 권한·감사 | 들어와서 무엇을 할 수 있고, 남는가 | sudo 정책, 권한 그룹, 세션 기록 |

## 구성 절차

### 1. 접근 경로를 하나로 모은다

관리 접근은 점프 서버(또는 접근제어 솔루션)를 통하게 하고, 서버의 관리 포트는 그 출처만 허용한다.

```
# Linux — 특정 출처만 SSH 허용 (firewalld)
firewall-cmd --permanent --new-zone=mgmt
firewall-cmd --permanent --zone=mgmt --add-source=10.10.20.0/24
firewall-cmd --permanent --zone=mgmt --add-service=ssh
firewall-cmd --permanent --zone=public --remove-service=ssh
firewall-cmd --reload
firewall-cmd --list-all-zones | head -40
```

```
# Azure — NSG 로 관리 포트 제한
az network nsg rule create -g <rg> --nsg-name <nsg> -n allow-ssh-mgmt \
  --priority 300 --direction Inbound --access Allow --protocol Tcp \
  --source-address-prefixes 10.10.20.0/24 --destination-port-ranges 22
```

```
# OCI — 보안 목록 대신 NSG 사용 권장
oci network nsg-security-rule add --nsg-id <nsg-ocid> --security-rules file://rules.json
```

**주의: 원격으로 작업하면서 SSH 규칙을 먼저 지우면 자기 자신이 잠긴다.** 새 허용 규칙을 넣고 접속을 확인한 뒤에 기존 규칙을 제거한다. 클라우드라면 시리얼 콘솔 접근 경로를 미리 확인해 둔다.

### 2. 계정을 분리하고 공용 계정을 없앤다

```
# root 직접 로그인 차단, 키 기반만 허용
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sshd -t && systemctl reload sshd
```

`sshd -t` 로 문법을 먼저 검사하고, `reload`(재시작 아님)를 쓴다. 설정이 잘못된 상태로 재시작하면 데몬이 안 올라와 접속이 끊긴다. 작업 중에는 **세션 하나를 따로 열어 둔 채로** 진행한다.

### 3. 권한은 작업 단위로 준다

```
# wheel 그룹에만 sudo, 암호 확인 유지
%wheel ALL=(ALL) ALL
# 특정 작업만 필요한 계정은 명령을 한정
appops ALL=(root) NOPASSWD: /bin/systemctl restart myapp
```

`NOPASSWD: ALL` 은 쓰지 않는다. 한정할 때도 셸을 띄울 수 있는 명령(`vi`, `less`, `find`)은 주지 않는다. 그것으로 셸 탈출이 된다.

Windows 쪽은 Active Directory 그룹으로 묶고, 도메인 관리자 계정과 일반 업무 계정을 반드시 분리한다. 관리 작업은 전용 관리 단말에서만 한다.

### 4. 남긴다

```
# 로그인 기록
last -F | head
lastb | head          # 실패 기록
journalctl -u sshd --since "24 hours ago" | grep -Ei "failed|invalid"
```

중앙 로그 서버로 전송해 두면 서버가 침해되어도 기록이 남는다. 로컬에만 있으면 지워진다.

## 운영 시 주의

- 방화벽·NSG 작업은 **잠금 위험이 가장 큰 작업**이다. 순서(허용 추가 → 확인 → 기존 제거)를 지키고, 되돌릴 명령을 미리 써 둔다.
- 퇴사·전배 시 계정 회수 절차가 없으면 통제가 무너진다. 분기별 계정 점검을 정례화한다.
- 서비스 계정은 사람 계정과 섞지 않는다. 로그인 셸을 주지 않고(`/sbin/nologin`), 대화형 로그인을 막는다.
- MFA 없는 VPN 은 사실상 계정 하나짜리 통제다. 관리망 접근에는 MFA 를 붙인다.
- 취약점 조치로 포트를 닫을 때 그 포트를 쓰는 연동이 있는지 먼저 확인한다. 모니터링 에이전트, 백업 에이전트가 자주 걸린다.

## 실무 권장

- 서버별 **허용 출처·허용 포트·접근 가능 계정** 표를 유지한다. 점검과 감사 대응이 이 표로 끝난다.
- 변경은 기록과 함께. 누가 왜 열었는지가 없으면 몇 달 뒤 아무도 닫지 못한다.
- 반기마다 "열려 있지만 쓰이지 않는 규칙"을 찾아 정리한다. 규칙은 쌓이기만 하고 줄지 않는다.

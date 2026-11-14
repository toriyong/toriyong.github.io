## 개요

클라우드 권한을 어떻게 나눌지에 대한 기준이다. 처음에 대충 잡으면 리소스가 늘어난 뒤에는 손을 못 댄다.

## 배경

권한 설계가 무너지는 경로는 거의 같다. 급해서 소유자 권한을 주고, 나중에 줄이려니 무엇이 깨질지 몰라서 못 줄이고, 그 상태로 굳는다.

막으려면 세 가지를 지키면 된다.

1. **개인이 아니라 그룹에 준다** — 개인 할당은 시간이 지나면 추적이 안 된다
2. **범위를 좁게 준다** — 전체가 아니라 필요한 구독·구획·리소스 그룹에만
3. **상시 권한과 임시 권한을 나눈다** — 관리자급은 평소에 없다가 필요할 때 받는다

## Azure 와 OCI

모델이 달라서 옮길 때 혼동이 생긴다.

| | Azure | OCI |
| --- | --- | --- |
| 방식 | 역할을 범위에 **할당** | 그룹이 구획에서 할 수 있는 일을 **문장으로 기술** |
| 범위 | 관리 그룹 → 구독 → 리소스 그룹 → 리소스 | 테넌시 → 구획(중첩 가능) |
| 상속 | 상위 범위 할당이 하위로 상속 | 상위 구획 정책이 하위에 적용 |

```bash
# Azure — 그룹에 역할을 범위로 할당
az role assignment create \
  --assignee-object-id <그룹 objectId> \
  --assignee-principal-type Group \
  --role "Virtual Machine Contributor" \
  --scope /subscriptions/<sub-id>/resourceGroups/rg-prod-app

# 현재 할당 확인 (상속분 포함)
az role assignment list --scope /subscriptions/<sub-id> --include-inherited -o table
```

```bash
# OCI — 정책 문장
# Allow group InfraOps to manage instance-family in compartment Prod
# Allow group InfraOps to read all-resources in tenancy
oci iam policy create --compartment-id <ocid> --name infraops-policy \
  --statements '["Allow group InfraOps to manage instance-family in compartment Prod"]' \
  --description "인프라 운영팀 권한"

oci iam policy list --compartment-id <ocid> --all --query 'data[*].{name:name,stmt:statements}'
```

## 역할을 나누는 기준

직무가 아니라 **작업**으로 나눈다. "개발팀"보다 "로그 조회", "VM 재기동", "배포" 가 재사용된다.

| 묶음 | 권한 | 대상 |
| --- | --- | --- |
| 조회 | Reader / read all-resources | 전원 |
| 운영 | VM·디스크·네트워크 관리 | 인프라 담당 |
| 배포 | 특정 리소스 그룹 Contributor | CI/CD 서비스 주체 |
| 보안 | 정책·로그 조회, 변경은 불가 | 보안 담당 |
| 관리 | 역할 할당, 구독 설정 | 소수, 임시로만 |

마지막 줄이 중요하다. **권한을 주는 권한**(Azure 의 User Access Administrator, OCI 의 manage policies)은 가장 위험하다. 이걸 가진 사람은 자기 권한을 스스로 올릴 수 있다.

## 점검

```bash
# Azure — 소유자급이 몇 명인지
az role assignment list --all --include-inherited \
  --query "[?roleDefinitionName=='Owner'].{who:principalName,scope:scope}" -o table

# 사용되지 않는 서비스 주체 찾기 (수동 검토 필요)
az ad sp list --all --query "[].{name:displayName,id:appId}" -o tsv | head
```

```bash
# OCI — 정책 전수 확인
oci iam compartment list --all --compartment-id-in-subtree true \
  --query 'data[*].{name:name,id:id}' -o table
```

숫자를 세어 관리한다. "소유자 3명"이 "소유자 11명"이 되는 걸 알아채는 장치가 필요하다.

## 운영 시 주의

- **사람 계정과 서비스 계정을 섞지 않는다.** 자동화용 주체는 별도로 만들고 권한을 최소로 준다.
- 서비스 주체의 비밀·인증서는 만료된다. 만료일을 모니터링에 넣는다. 갑자기 배포가 안 되는 원인 1순위다.
- 가능하면 비밀 대신 **관리 ID**(Azure Managed Identity)나 **인스턴스 주체**(OCI Instance Principal)를 쓴다. 자격 증명을 보관할 필요가 없어진다.
- 상속을 잊지 않는다. 관리 그룹에 준 역할은 하위 구독 전부에 적용된다. "리소스 그룹에만 줬는데 왜 다 보이지"의 답이 대개 이것이다.
- 권한을 뺄 때는 영향 범위를 먼저 본다. 배포 파이프라인이 그 권한으로 돌고 있는 경우가 있다.

## 실무 권장

- **역할 정의표**를 한 장으로 유지한다. 그룹명, 권한, 범위, 사유, 승인자. 이게 없으면 분기 점검이 불가능하다.
- 관리자급은 상시 보유를 없애고 **승인 기반 임시 권한**으로 돌린다. Azure 는 PIM, OCI 는 별도 그룹과 승인 절차로 구현한다.
- 분기마다 "쓰이지 않는 할당"을 걷어낸다. 권한은 쌓이기만 하고 줄지 않는다.
- 로그는 권한과 분리된 곳에 모은다. 운영 권한으로 감사 로그를 지울 수 있으면 추적성이 없는 것과 같다.

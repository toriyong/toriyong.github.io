## 개요

클라우드를 쓰기 시작할 때 먼저 만들어 두는 공통 기반이다. 계정·네트워크·권한·로그 체계를 미리 정해 두지 않으면, 리소스가 늘어난 뒤에는 되돌리기 어렵다.

## 배경

처음에는 구독 하나에 리소스를 다 넣고 시작한다. 그러다 운영과 개발이 섞이고, 권한을 구분할 수 없게 되고, 비용을 누가 쓴 것인지 알 수 없게 된다. 랜딩존은 이 지점을 앞당겨 정리해 두는 작업이다.

정해야 할 것은 다섯 가지다.

| 영역 | 정하는 것 |
| --- | --- |
| 계층 | 구독·구획 분리 기준 (환경별 / 조직별) |
| 네트워크 | 주소 체계, 허브-스포크, 온프레미스 연결 |
| 권한 | 역할 정의와 할당 범위 |
| 거버넌스 | 정책, 태그, 비용 구분 |
| 로그 | 수집 대상, 보관처, 보관 기간 |

## Azure 와 OCI 의 대응 관계

구조가 비슷해서 한쪽을 알면 다른 쪽이 빠르다.

| 개념 | Azure | OCI |
| --- | --- | --- |
| 계층 | 관리 그룹 → 구독 → 리소스 그룹 | 테넌시 → 구획(Compartment) |
| 네트워크 | VNet / 서브넷 / NSG | VCN / 서브넷 / NSG·보안목록 |
| 라우팅 | 라우트 테이블, 피어링 | 라우트 테이블, DRG, 피어링 |
| 권한 | RBAC 역할 할당 | IAM 정책(구획 단위 문장) |
| 정책 | Azure Policy | 보안 영역(Security Zones), 할당량 |
| 로그 | Azure Monitor / Log Analytics | Logging, Audit |

가장 큰 차이는 권한 모델이다. Azure 는 "역할을 범위에 할당"하고, OCI 는 "그룹이 구획에서 무엇을 할 수 있다"를 문장으로 쓴다.

```
# OCI 정책 예시 — 그룹과 구획을 묶어 한 줄로
Allow group InfraOps to manage instance-family in compartment Prod
Allow group InfraOps to read all-resources in tenancy
```

## 네트워크 설계

허브-스포크가 기본형이다. 허브에 온프레미스 연결과 공통 보안 장비를 두고, 업무 네트워크는 스포크로 붙인다.

주소 체계는 처음에 넉넉하게 나눈다. 온프레미스와 겹치면 연결 단계에서 막히고, 이미 배포된 뒤에는 바꿀 수 없다.

```
# Azure — VNet 과 서브넷
az network vnet create -g <rg> -n vnet-hub --address-prefixes 10.20.0.0/16 \
  --subnet-name snet-shared --subnet-prefixes 10.20.1.0/24

# 피어링 (양방향 각각 생성해야 한다)
az network vnet peering create -g <rg> -n hub-to-spoke1 \
  --vnet-name vnet-hub --remote-vnet <spoke-id> --allow-vnet-access
az network vnet peering create -g <rg> -n spoke1-to-hub \
  --vnet-name vnet-spoke1 --remote-vnet <hub-id> --allow-vnet-access
```

```
# OCI — VCN 과 DRG 연결
oci network vcn create --compartment-id <ocid> --cidr-blocks '["10.30.0.0/16"]' \
  --display-name vcn-hub
oci network drg-attachment create --drg-id <drg-ocid> --vcn-id <vcn-ocid>
```

피어링은 **양쪽에서 각각 만들어야** 통한다. 한쪽만 만들고 안 된다고 보는 경우가 흔하다. 그리고 피어링이 되어도 라우트 테이블과 NSG 가 허용하지 않으면 패킷은 가지 않는다. 연결 문제는 이 세 군데를 순서대로 본다. 피어링 상태 → 라우트 → 보안 규칙.

## 하이브리드 연결

온프레미스와 붙일 때 선택지는 전용선(ExpressRoute / FastConnect)과 VPN 이다. 전용선은 대역과 지연이 안정적이고, VPN 은 빠르게 붙일 수 있다. 실무에서는 전용선을 주 경로로 두고 VPN 을 백업 경로로 쓰는 구성이 많다.

확인해야 할 것은 세 가지다. 주소 중복 여부, DNS 해석 경로(온프레미스 도메인을 클라우드에서 어떻게 찾을지), 그리고 **경로가 비대칭이 되지 않는지**다. 비대칭 경로는 방화벽 상태 추적에 걸려 연결이 간헐적으로 끊기는 형태로 나타나는데, 원인 찾기가 까다롭다.

## 운영 시 주의

- 태그를 처음부터 강제한다. 나중에 붙이는 비용 구분은 거의 안 된다. 최소 `환경`, `담당`, `서비스` 세 개.
- 권한은 개인이 아니라 그룹에 준다. 개인 할당은 시간이 지나면 추적이 불가능해진다.
- 소유자·관리자급 권한 할당은 수를 세어 관리한다. 늘어난 것을 알아채는 장치가 필요하다.
- 로그는 별도 구독·구획에 모은다. 운영 권한으로 로그를 지울 수 있으면 감사 추적성이 없는 것과 같다.
- 리전과 가용성 도메인 배치는 복구 요건에서 역산한다. 먼저 배포하고 나중에 옮기는 것은 사실상 재구축이다.

## 실무 권장

- 랜딩존 설계서는 길게 쓰지 말고 **주소 할당표, 구독·구획 목록, 역할 정의표** 세 장으로 유지한다. 길면 아무도 갱신하지 않는다.
- 공식 가이드(Azure CAE / OCI 아키텍처 센터)를 기준으로 두되, 전부 구현하지 않는다. 규모에 맞게 계층을 줄이고 시작한다.
- 구성은 가능하면 코드로 남긴다(Bicep, Terraform). 수동으로 만든 것은 1년 뒤에 왜 그렇게 되어 있는지 알 수 없다.

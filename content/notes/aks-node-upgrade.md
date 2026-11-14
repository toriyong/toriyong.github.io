## 개요

AKS 클러스터를 서비스 중단 없이 상위 버전으로 올리는 절차다. 컨트롤 플레인과 노드풀을 나눠 올리고, API 변경으로 깨질 리소스를 먼저 찾아내는 것이 핵심이다.

## 배경

쿠버네티스는 마이너 버전마다 API 가 정리된다. 더 이상 제공되지 않는 API 를 쓰는 매니페스트는 업그레이드 후 배포가 실패한다. 이미 돌고 있는 워크로드는 당장 멈추지 않지만, 재배포하는 순간 터진다.

AKS 는 N-2 정책으로 지원 버전을 관리한다. 미루면 한 번에 여러 단계를 올려야 하고 위험이 커진다. 마이너 버전은 건너뛸 수 없으므로 1.30 → 1.32 는 1.31 을 거쳐야 한다.

## 사전 점검

```
# 현재 버전과 올릴 수 있는 버전
az aks show -g <rg> -n <cluster> --query "{cp:kubernetesVersion, rg:nodeResourceGroup}" -o table
az aks get-upgrades -g <rg> -n <cluster> -o table

# 노드풀별 버전
az aks nodepool list -g <rg> --cluster-name <cluster> -o table

# 더 이상 제공되지 않는 API 사용 여부
kubectl get --raw /metrics | grep apiserver_requested_deprecated_apis
```

PodDisruptionBudget 과 레플리카 수도 함께 본다. 레플리카가 1인 서비스는 노드가 비워질 때 반드시 끊긴다.

```
kubectl get pdb -A
kubectl get deploy -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,REP:.spec.replicas
```

## 절차

1. **컨트롤 플레인만 먼저 올린다.** 노드는 그대로 둔다.

```
az aks upgrade -g <rg> -n <cluster> --kubernetes-version 1.31.x --control-plane-only
```

2. 클러스터 상태와 주요 서비스 동작을 확인한다.

```
kubectl get nodes
kubectl get pods -A | grep -v Running
```

3. **노드풀을 하나씩 올린다.** 여러 풀을 동시에 올리지 않는다.

```
az aks nodepool upgrade -g <rg> --cluster-name <cluster> -n <pool> \
  --kubernetes-version 1.31.x --max-surge 1
```

`--max-surge` 는 한 번에 추가로 띄울 노드 수다. 1 이면 새 노드 하나를 띄우고 기존 노드 하나를 비우는 식으로 천천히 간다. 빠르게 하려면 `33%` 처럼 비율로 줄 수 있지만, 그만큼 동시에 비워지는 노드가 늘어난다.

4. 풀마다 끝날 때 파드 재배치와 서비스 상태를 확인하고 다음 풀로 넘어간다.

## 운영 시 주의

- **노드가 비워질 때 파드가 옮겨 간다.** 레플리카 1인 서비스, 로컬 디스크를 쓰는 파드, PDB 가 없는 워크로드는 이때 끊긴다.
- PDB 를 너무 빡빡하게 잡으면 노드가 영영 비워지지 않아 업그레이드가 멈춘다. `minAvailable` 이 레플리카 수와 같으면 안 된다.
- 노드풀의 VM 크기나 쿼터가 부족하면 `--max-surge` 로 새 노드를 못 띄워 실패한다. 구독 쿼터를 미리 본다.
- 업그레이드 중에는 배포를 멈춘다. CI 가 돌면 상태 판단이 어려워진다.
- 인그레스 컨트롤러와 CNI, CSI 드라이버 같은 애드온은 버전 호환을 따로 확인한다. 클러스터만 올리고 애드온이 구버전이면 문제가 나중에 드러난다.

## 실무 권장

- 개발 클러스터에서 같은 순서로 먼저 돌려 본다. 소요 시간을 재 두면 작업 공지에 쓸 수 있다.
- 작업계획서에 **롤백 기준**을 적는다. 쿠버네티스는 다운그레이드가 안 되므로, 롤백은 "새 노드풀을 구버전으로 만들어 워크로드를 옮긴다"가 된다. 이걸 미리 정해 두지 않으면 문제 생겼을 때 선택지가 없다.
- 분기마다 한 단계씩 올리는 주기를 만들어 둔다. 몰아서 올리는 것보다 매번 가볍게 가는 편이 안전하다.

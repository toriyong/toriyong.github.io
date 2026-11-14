## 개요

쿠버네티스에서 파드가 알 수 없는 이유로 죽거나, 노드가 멀쩡한데 스케줄이 안 될 때, 대부분 원인은 리소스 요청·제한 설정이다.

## 배경

파드마다 두 값을 줄 수 있다.

| 항목 | 역할 |
| --- | --- |
| `requests` | 스케줄러가 노드를 고를 때 쓰는 **예약량** |
| `limits` | 실제로 넘지 못하는 **상한** |

핵심은 **스케줄링은 requests 로만 판단한다**는 점이다. limits 는 스케줄링에 영향을 주지 않는다. 그래서 requests 를 작게 주면 노드에 파드가 잔뜩 올라가고, 실제 사용량이 늘면 노드가 터진다.

CPU 와 메모리는 초과했을 때 동작이 다르다. 이걸 모르면 원인을 못 찾는다.

| 자원 | limits 초과 시 |
| --- | --- |
| CPU | **스로틀링** — 느려지지만 죽지는 않음 |
| 메모리 | **OOMKilled** — 컨테이너가 즉시 종료됨 |

## 진단

```
# 파드가 왜 죽었는지 — 여기부터
kubectl describe pod <파드명> | sed -n '/Last State/,/Ready/p'
kubectl get pod <파드명> -o jsonpath='{.status.containerStatuses[*].lastState.terminated.reason}'
```

`OOMKilled` 가 나오면 메모리 limits 초과다. `Error` 면 애플리케이션 문제다.

```
# 실제 사용량 (metrics-server 필요)
kubectl top pod -A --sort-by=memory | head -20
kubectl top node

# 노드의 예약 현황 — 실제 사용량이 아니라 requests 합계다
kubectl describe node <노드명> | sed -n '/Allocated resources/,/Events/p'
```

`Allocated resources` 가 100% 에 가까우면 **노드가 한가해 보여도 새 파드가 안 올라간다.** `kubectl top node` 는 20% 인데 스케줄이 안 되는 상황이 이것이다.

```
# 스케줄 실패 사유
kubectl get events --sort-by=.lastTimestamp | grep -i failedscheduling
kubectl describe pod <Pending 파드> | tail -20
```

## 값 정하기

추측하지 말고 측정한다.

1. limits 없이 또는 넉넉하게 두고 일정 기간 운영한다
2. `kubectl top` 이나 모니터링에서 피크를 본다
3. **requests = 평상시 사용량**, **limits = 피크 + 여유**

```yaml
resources:
  requests:
    cpu: "200m"        # 평상시
    memory: "256Mi"
  limits:
    cpu: "1000m"       # 피크 허용
    memory: "512Mi"    # 여유를 넉넉히
```

메모리는 **requests 와 limits 를 같게 두는 것**도 방법이다. 그러면 QoS 가 `Guaranteed` 가 되어 노드 메모리가 부족할 때 가장 나중에 퇴출된다.

| QoS | 조건 | 퇴출 순서 |
| --- | --- | --- |
| Guaranteed | requests == limits (CPU·메모리 모두) | 마지막 |
| Burstable | requests < limits | 중간 |
| BestEffort | 아무것도 설정 안 함 | **가장 먼저** |

아무 설정도 없는 파드가 제일 먼저 죽는다. 중요한 워크로드에 리소스 설정이 없는 건 위험하다.

## 운영 시 주의

- **CPU limits 를 낮게 잡으면 조용히 느려진다.** 죽지 않으니 모니터링에도 안 잡힌다. 응답 지연의 숨은 원인이다.
- JVM 같은 런타임은 컨테이너 limits 를 인식하는 옵션을 켜야 한다. 안 그러면 호스트 전체 메모리를 기준으로 힙을 잡고 OOMKilled 가 난다.
- 네임스페이스에 `LimitRange` 와 `ResourceQuota` 를 걸어 두면 설정 없는 파드가 들어오는 걸 막을 수 있다.
- 노드 업그레이드나 드레인 시 requests 합계가 남은 노드 용량을 넘으면 파드가 Pending 으로 남는다. 업그레이드 전에 여유를 확인한다.

## 실무 권장

- 새 워크로드는 **requests 를 조금 넉넉하게** 시작해서 줄여 나간다. 반대 방향은 장애를 거친다.
- OOMKilled 발생 횟수를 모니터링 항목에 넣는다. 재시작으로 복구되니 아무도 모르고 지나간다.
- 리소스 설정을 바꾸면 파드가 재생성된다. 무중단이 필요하면 PDB 와 레플리카 수를 먼저 확인한다.

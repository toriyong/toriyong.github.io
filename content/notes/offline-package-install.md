## 개요

인터넷이 안 되는 폐쇄망 서버에 패키지를 설치하는 방법이다. 의존성 때문에 막히는 지점이 정해져 있어서, 순서만 알면 어렵지 않다.

## 배경

금융·공공 쪽 IDC 는 서버가 외부로 못 나간다. `dnf install` 한 줄이 안 먹는다. 선택지는 셋이다.

| 방법 | 적합한 상황 | 품 |
| --- | --- | --- |
| 패키지 파일만 반입 | 한두 개 설치 | 적음, 의존성 수작업 |
| 로컬 저장소 구축 | 서버가 여럿, 지속 운영 | 초기 큼, 이후 편함 |
| 저장소 미러링 | 패치까지 폐쇄망에서 관리 | 큼, 용량 필요 |

서버가 다섯 대만 넘어가도 두 번째가 이익이다.

## 패키지 파일만 반입

의존성까지 한 번에 받는 게 핵심이다. 외부망 장비에서 받는다. **같은 배포판·같은 버전**이어야 한다.

```
# RHEL 계열 — 의존성 포함해서 내려받기만
dnf download --resolve --alldeps --destdir=/tmp/pkgs <패키지명>

# Ubuntu
apt-get install --download-only -o Dir::Cache::archives=/tmp/pkgs <패키지명>
```

폐쇄망으로 옮긴 뒤 설치한다.

```
# RHEL — 디렉터리 안의 것만 쓰도록
dnf install --disablerepo="*" /tmp/pkgs/*.rpm

# Ubuntu
dpkg -i /tmp/pkgs/*.deb && apt-get install -f
```

`rpm -ivh *.rpm` 보다 `dnf install *.rpm` 이 낫다. 설치 순서를 알아서 정리해 준다.

## 로컬 저장소 구축

폐쇄망 안에 저장소 역할을 할 서버를 하나 둔다.

```
# 저장소 서버에서
dnf install -y createrepo_c
mkdir -p /var/www/repo/base
cp /tmp/pkgs/*.rpm /var/www/repo/base/
createrepo_c /var/www/repo/base

# 패키지를 추가한 뒤에는 반드시 다시
createrepo_c --update /var/www/repo/base
```

HTTP 로 서비스하고, 각 서버에 저장소 정의를 내린다.

```
# /etc/yum.repos.d/local.repo
[local-base]
name=Local Base
baseurl=http://<저장소서버>/repo/base
enabled=1
gpgcheck=0
```

```
dnf clean all
dnf repolist
dnf makecache
```

`gpgcheck=0` 은 서명 검증을 끄는 것이다. 편하지만 **패키지가 바뀌어도 모른다.** 배포판 GPG 키를 같이 반입해 `gpgcheck=1` 로 두는 편이 맞다.

```
rpm --import /tmp/RPM-GPG-KEY-redhat-release
```

## 막히는 지점

**버전이 미묘하게 다르다.** 외부망 장비가 8.9 인데 대상 서버가 8.6 이면 받은 패키지가 더 상위 라이브러리를 요구한다. 받는 쪽 장비를 대상과 같은 마이너 버전으로 맞추거나, 컨테이너로 같은 버전 환경을 만들어 받는다.

```
podman run --rm -v /tmp/pkgs:/pkgs rockylinux:8.6 \
  bash -c "dnf download --resolve --alldeps --destdir=/pkgs <패키지명>"
```

**이미 설치된 것은 안 받아진다.** `--resolve` 는 받는 쪽 장비 기준으로 판단해서, 거기 이미 있는 의존성은 건너뛴다. 깨끗한 환경에서 받는 게 안전하다.

**Python·Node 모듈은 별개다.** `pip download -d /tmp/wheels <패키지>` 로 받아 `pip install --no-index --find-links=/tmp/wheels` 로 설치한다. 컴파일이 필요한 모듈은 대상과 같은 환경에서 받아야 한다.

## 운영 시 주의

- 반입 매체는 보안 절차를 탄다. 사전 신청·검사 시간을 일정에 넣는다.
- 설치 전 어떤 패키지가 올라가는지 목록으로 남긴다. 되돌릴 때 필요하다.
- 저장소 서버 디스크는 넉넉하게. 기본 저장소 전체 미러는 수십 GB 가 된다.
- 로컬 저장소도 **보안 패치 반영 경로**를 정해둔다. 안 그러면 구버전으로 고정된 서버 무리가 생긴다.

## 실무 권장

- 자주 쓰는 패키지 묶음(개발 도구, 모니터링 에이전트, 백업 에이전트)을 미리 받아둔다. 급할 때 반입 절차를 또 타지 않아도 된다.
- 저장소 갱신 날짜를 서버 목록 옆에 적어둔다. 마지막 갱신이 언제인지가 취약점 대응의 출발점이다.

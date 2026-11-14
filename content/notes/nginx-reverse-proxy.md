## 개요

NGINX 를 리버스 프록시로 두고 뒤쪽 애플리케이션으로 넘길 때의 설정과, 운영하며 자주 만나는 문제들이다.

## 배경

리버스 프록시를 두는 이유는 보통 셋이다. TLS 종료를 한곳에서 하려고, 여러 백엔드를 한 주소로 묶으려고, 그리고 백엔드를 직접 노출하지 않으려고.

문제는 **프록시를 거치면서 원래 요청 정보가 사라진다**는 점이다. 백엔드는 클라이언트 IP 대신 프록시 IP 를 보고, HTTPS 로 들어온 요청을 HTTP 로 인식한다. 로그인 리다이렉트가 `http://` 로 나가 무한 루프가 되는 전형적인 증상이 여기서 나온다.

## 기본 설정

```nginx
upstream app_backend {
    server 10.0.1.11:8080 max_fails=3 fail_timeout=10s;
    server 10.0.1.12:8080 max_fails=3 fail_timeout=10s;
    keepalive 32;
}

server {
    listen 443 ssl;
    http2 on;
    server_name app.example.com;

    ssl_certificate     /etc/nginx/certs/app.crt;
    ssl_certificate_key /etc/nginx/certs/app.key;
    ssl_protocols       TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://app_backend;

        # 원래 요청 정보를 넘긴다 — 빠뜨리면 위 문제가 생긴다
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;

        # upstream keepalive 를 쓰려면 둘 다 필요하다
        proxy_http_version 1.1;
        proxy_set_header Connection "";

        proxy_connect_timeout 5s;
        proxy_send_timeout    60s;
        proxy_read_timeout    60s;
    }
}
```

`keepalive` 를 선언해도 `proxy_http_version 1.1` 과 `Connection ""` 이 없으면 매 요청 새 연결을 맺는다. 부하가 높을 때 차이가 크다.

## 적용

```
nginx -t                 # 문법 검사 — 항상 먼저
systemctl reload nginx   # restart 아님
```

`reload` 는 기존 연결을 끊지 않고 새 설정을 적용한다. `restart` 는 끊는다. 설정이 틀린 상태로 `restart` 하면 올라오지 않는다.

## 자주 만나는 문제

**502 Bad Gateway** — 백엔드에 못 붙는다. 순서대로 본다.

```
curl -sv http://10.0.1.11:8080/health      # 프록시 서버에서 직접
ss -tlnp | grep 8080                       # 백엔드에서 리슨 확인
getenforce                                 # SELinux
```

SELinux 가 켜진 RHEL 계열에서 **NGINX 가 백엔드로 못 나가는 경우**가 흔하다. 로그에 `Permission denied` 가 보인다.

```
setsebool -P httpd_can_network_connect 1
```

**504 Gateway Timeout** — 백엔드가 느리다. `proxy_read_timeout` 을 늘리기 전에 백엔드가 왜 느린지를 본다. 타임아웃만 늘리면 프록시 워커가 묶여 전체가 느려진다.

**413 Request Entity Too Large** — 업로드 크기 제한이다.

```nginx
client_max_body_size 100m;
```

백엔드에도 같은 제한이 있을 수 있으니 양쪽을 맞춘다.

**WebSocket 이 안 붙는다** — 업그레이드 헤더를 넘겨야 한다.

```nginx
location /ws/ {
    proxy_pass http://app_backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade    $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
}
```

## 운영 시 주의

- **헤더 네 개(`Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`)는 세트로 넣는다.** 하나만 빠져도 증상이 나중에 이상하게 나타난다.
- 백엔드는 `X-Forwarded-*` 를 **신뢰할 프록시에서 올 때만** 믿도록 설정한다. 아무나 보낼 수 있는 헤더라 그대로 믿으면 IP 위조가 된다.
- 인증서 만료는 모니터링에 넣는다. 갱신 자동화를 걸었어도 실패할 수 있다.
- 로그에 `$upstream_response_time` 을 넣어두면 백엔드가 느린지 프록시가 느린지 바로 갈린다.

```nginx
log_format  proxied '$remote_addr $status $request_time $upstream_response_time "$request"';
```

## 실무 권장

- 설정 변경 전에 현재 파일을 날짜 붙여 복사해 둔다. `nginx -t` 는 문법만 보지 의도는 못 본다.
- `upstream` 에 서버가 하나뿐이어도 `upstream` 블록으로 쓴다. 나중에 늘릴 때 설정을 안 건드린다.
- 헬스 체크 경로는 인증 없이 열어두되, 내부에서만 접근되게 제한한다.

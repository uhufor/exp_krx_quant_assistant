# launchd 설정

## 설치

```bash
bash ops/setup.sh
```

## 수동 실행/중지

```bash
# 수동 실행
launchctl start com.quant-krx.daily

# 등록 해제
launchctl unload ~/Library/LaunchAgents/com.quant-krx.daily.plist
```

## 로그 확인

```bash
tail -f logs/launchd.stdout.log
tail -f logs/launchd.stderr.log
```

## 실행 시각

매일 **15:35 KST** (UTC 06:35) — 한국 주식시장 마감(15:30) 후 5분

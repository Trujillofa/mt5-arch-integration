# Headless Single test — XAUUSD H1

- Range: **2024.06.01 → 2024.09.01**
- Exit code: **0**
- Status: **OK**
- Agent: `/home/yderf/.mt5-vantage/drive_c/Program Files/Vantage International MT5/Tester/logs/20260806.log`
- Wine: `/tmp/mt5-tester-headless.log`

## Journal
### `shutdown with[^\r\n]*`
```
shutdown with 0
```
### `ForexHtfFibTester v1\.\d+ ON[^\r\n]*`
```
ForexHtfFibTester v1.30 ON XAUUSD PERIOD_H1 mode=FX_MODE_INTRADAY RSI<=42/>=58 rsiMA=off zone=ON bias=on researchFB=off liveTrade=yes SL=2.0xATR TP=3.0xATR lots=0.01 maxSpreadPips=0.0
ForexHtfFibTester v1.30 ON XAUUSD PERIOD_H1 mode=FX_MODE_INTRADAY RSI<=42/>=58 rsiMA=off zone=ON bias=on researchFB=off liveTrade=yes SL=2.0xATR TP=3.0xATR lots=0.01 maxSpreadPips=0.0
ForexHtfFibTester v1.30 ON XAUUSD PERIOD_H1 mode=FX_MODE_INTRADAY RSI<=42/>=58 rsiMA=off zone=ON bias=on researchFB=off liveTrade=yes SL=2.0xATR TP=3.0xATR lots=0.01 maxSpreadPips=0.0
ForexHtfFibTester v1.40 ON XAUUSD PERIOD_H1 eaFib=yes zone=ON bias=on RSI<=42/>=58 htfBars=800 pivots=94 swing=-1 fib=1 liveTrade=yes lots=0.01 SL=2.0x TP=3.0x
ForexHtfFibTester v1.40 ON XAUUSD PERIOD_H1 eaFib=yes zone=ON bias=on RSI<=42/>=58 htfBars=800 pivots=91 swing=1 fib=1 liveTrade=yes lots=0.01 SL=2.0x TP=3.0x
ForexHtfFibTester v1.40 ON XAUUSD PERIOD_H1 eaFib=yes zone=ON bias=on RSI<=40/>=60 htfBars=800 pivots=102 swing=-1 fib=1 liveTrade=yes lots=0.01 SL=2.0x TP=3.0x
```
### `EaFib rebuild[^\r\n]*`
```
EaFib rebuild tf=PERIOD_H4 n=800 pivots=100 swing=-1 fib=1 f618=2517.0467 f786=2523.4559 hi=2531.62 lo=2493.47
EaFib rebuild tf=PERIOD_H4 n=800 pivots=101 swing=-1 fib=1 f618=2508.36002 f786=2518.58954 hi=2531.62 lo=2470.73
EaFib rebuild tf=PERIOD_H4 n=800 pivots=100 swing=-1 fib=1 f618=2508.36002 f786=2518.58954 hi=2531.62 lo=2470.73
EaFib rebuild tf=PERIOD_H4 n=800 pivots=100 swing=1 fib=1 f618=2492.1411000000003 f786=2482.7247 hi=2526.78 lo=2470.73
EaFib rebuild tf=PERIOD_H4 n=800 pivots=101 swing=1 fib=1 f618=2513.23336 f786=2508.95272 hi=2528.98 lo=2503.5
EaFib rebuild tf=PERIOD_H4 n=800 pivots=100 swing=-1 fib=1 f618=2515.48394 f786=2521.41938 hi=2528.98 lo=2493.65
```
### `DIAG\[OnTester\][^\r\n]*`
```
DIAG[OnTester] bars=3482 spreadBlock=0 bufFail=0 fibValid=0 swing!=0=0 zoneL/S=0/0 regimeL/S=0/0 rsiL/S=0/0 sigL/S=0/0 researchCalls=0 rsiFail/inv=0/0 edgeRawL/S=0/0 biasBlock=0 researchHits=0 rsiMinMax=1000.0/-1000.0 rsiN=0 entryOK/fail=0/0 flags zone=1 bias=1
DIAG[OnTester] bars=3482 spreadBlock=0 bufFail=0 fibValid=0 swing!=0=0 zoneL/S=0/0 regimeL/S=0/0 rsiL/S=0/0 sigL/S=0/0 researchCalls=0 rsiFail/inv=0/0 edgeRawL/S=0/0 biasBlock=0 researchHits=0 rsiMinMax=1000.0/-1000.0 rsiN=0 entryOK/fail=0/0 flags zone=1 bias=1
DIAG[OnTester] bars=5911 spreadBlock=0 bufFail=0 fibValid=0 swing!=0=0 zoneL/S=0/0 regimeL/S=0/0 rsiL/S=0/0 sigL/S=0/0 researchCalls=0 rsiFail/inv=0/0 edgeRawL/S=0/0 biasBlock=0 researchHits=0 rsiMinMax=1000.0/-1000.0 rsiN=0 entryOK/fail=0/0 flags zone=1 bias=1
DIAG[OnTester] bars=5911 spreadBlock=0 htfBars=800 pivots=90 fibValid=5911 swing!=0=5911 zoneL/S=168/298 rsiL/S=1034/2085 sigL/S=18/5 researchHits=0 rsiMinMax=19.22886068024458/87.93317236835546 entryOK/fail=14/0 flags zone=1 bias=1
DIAG[OnTester] bars=5455 spreadBlock=0 htfBars=800 pivots=97 fibValid=5455 swing!=0=5455 zoneL/S=238/260 rsiL/S=1106/1862 sigL/S=16/9 researchHits=0 rsiMinMax=13.114090667003495/88.49588741868644 entryOK/fail=17/1 flags zone=1 bias=1
DIAG[OnTester] bars=1490 spreadBlock=0 htfBars=800 pivots=100 fibValid=1490 swing!=0=1490 zoneL/S=69/134 rsiL/S=245/463 sigL/S=5/5 researchHits=0 rsiMinMax=14.739518068271053/86.43884062457637 entryOK/fail=6/0 flags zone=1 bias=1
```
### `OnTester summary[^\r\n]*`
```
OnTester summary trades=0.0 profit=0.0 pf=0.0 maxDD%=0.0
OnTester summary trades=0.0 profit=0.0 pf=0.0 maxDD%=0.0
OnTester summary trades=0.0 profit=0.0 pf=0.0 maxDD%=0.0
OnTester summary trades=14.0 profit=-220.4 pf=0.2552796080418989 maxDD%=2.2425
OnTester summary trades=17.0 profit=-20.569999999999993 pf=0.840740167234438 maxDD%=0.644904593908048
OnTester summary trades=6.0 profit=-3.0299999999999976 pf=0.9240981963927856 maxDD%=0.35827279001943046
```
### `final balance[^\r\n]*`
```
final balance 10000.00 USD
final balance 10000.00 USD
final balance 10000.00 USD
final balance 9779.60 USD
final balance 9979.43 USD
final balance 9996.97 USD
```
### `OnTester result[^\r\n]*`
```
OnTester result -1
OnTester result -1
OnTester result -1
OnTester result 0.2552796080418989
OnTester result 0.840740167234438
OnTester result 0.9240981963927856
```
### `Test passed[^\r\n]*`
```
Test passed in 0:00:00.382 (including ticks preprocessing 0:00:00.035).
Test passed in 0:00:00.478 (including ticks preprocessing 0:00:00.056).
Test passed in 0:00:00.545 (including ticks preprocessing 0:00:00.052).
Test passed in 0:00:00.494 (including ticks preprocessing 0:00:00.053).
Test passed in 0:00:00.290 (including ticks preprocessing 0:00:00.020).
test passed with result "successfully finished" in 0:00:00.290
```

## Reports
- `/home/yderf/.mt5-vantage/drive_c/Program Files/Vantage International MT5/reports/htf_fib_XAUUSD_H1_20260806_092553.htm` (43342 bytes)
- `/home/yderf/.mt5-vantage/drive_c/Program Files/Vantage International MT5/reports/htf_fib_XAUUSD_H1_20260806_092553-holding.png` (16657 bytes)
- `/home/yderf/.mt5-vantage/drive_c/Program Files/Vantage International MT5/reports/htf_fib_XAUUSD_H1_20260806_092553-mfemae.png` (33563 bytes)
- `/home/yderf/.mt5-vantage/drive_c/Program Files/Vantage International MT5/reports/htf_fib_XAUUSD_H1_20260806_092553-hst.png` (39901 bytes)
- `/home/yderf/.mt5-vantage/drive_c/Program Files/Vantage International MT5/reports/htf_fib_XAUUSD_H1_20260806_092553.png` (23603 bytes)

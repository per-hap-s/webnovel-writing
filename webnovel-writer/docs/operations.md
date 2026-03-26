# 椤圭洰缁撴瀯涓庤繍缁?

## 鐩綍灞傜骇

杩愯鏃跺缓璁粺涓€浣跨敤杩欏嚑涓矾寰勬蹇碉細

1. `WORKSPACE_ROOT`锛氫綘鐨勫伐浣滃尯鏍圭洰褰曘€?
2. `WORKSPACE_ROOT/.webnovel/`锛氬伐浣滃尯绾ф寚閽堜笌缂撳瓨鐩綍銆?
3. `PROJECT_ROOT`锛氱湡瀹炲皬璇撮」鐩牴鐩綍锛岀敱 `webnovel init` 鍒涘缓銆?
4. `PLUGIN_ROOT`锛氭彃浠舵垨浠撳簱浠ｇ爜鐩綍銆?

### Workspace 鐩綍

```text
workspace-root/
鈹溾攢鈹€ .webnovel/
鈹?  鈹溾攢鈹€ current-project
鈹?  鈹斺攢鈹€ settings.json
鈹溾攢鈹€ 灏忚A/
鈹溾攢鈹€ 灏忚B/
鈹斺攢鈹€ ...
```

### 灏忚椤圭洰鐩綍

```text
project-root/
鈹溾攢鈹€ .webnovel/
鈹溾攢鈹€ 姝ｆ枃/
鈹溾攢鈹€ 澶х翰/
鈹斺攢鈹€ 璁惧畾闆?
```

## Dashboard 宸ヤ綔鍙板惎鍔ㄨ涔?

褰撳墠榛樿鍏ュ彛宸茬粡鏄€滃叏灞€澹虫ā寮忊€濓細

- 鍚姩鑴氭湰榛樿涓嶅啀瑕佹眰 `PROJECT_ROOT`銆?
- 鍙屽嚮 `Start-Webnovel-Writer.bat` 浼氱洿鎺ュ惎鍔?Web 宸ヤ綔鍙般€?
- 宸ヤ綔鍙版帴鍙ｈ礋璐ｉ」鐩€夋嫨銆侀」鐩敞鍐屻€佹渶杩戦」鐩?鍥哄畾椤圭洰銆佸伐鍏峰姩浣溿€?
- 椤圭洰椤电户缁娇鐢?`project_root` 鏌ヨ鍙傛暟浣滀负褰撳墠娲诲姩椤圭洰鐨勬潈濞佹潵婧愩€?
- 鏃犳椿鍔ㄩ」鐩椂锛岄」鐩瀷 API 搴旇繑鍥?`PROJECT_NOT_SELECTED`锛岃€屼笉鏄湪搴旂敤鍚姩闃舵宕╂簝銆?

宸ヤ綔鍖烘敞鍐岄渶瑕佺淮鎶わ細

- `.webnovel/current-project`
- 宸ヤ綔鍖烘敞鍐岃〃涓殑 `current_project_root`
- `recent_projects[]`
- `pinned_project_roots[]`

## Dashboard 鐪熷疄澶嶉獙鎿嶄綔鍙ｅ緞

### 鍚姩鍣ㄥ喎閲嶅惎鏃佽瘉

褰撻渶瑕侀獙璇佲€滃潖瀹炰緥鏇挎崲 / 鍐烽噸鍚€濇椂锛屼紭鍏堜娇鐢ㄩ殧绂荤鍙ｅ彈鎺у満鏅紝涓嶇洿鎺ュ己鏉€姝ｅ湪鏈嶅姟鐨勪富瀹炰緥銆?

鎺ㄨ崘姝ラ锛?

1. 閫変竴涓湭鍗犵敤绔彛锛屼緥濡?`8877`銆?
2. 鍚姩涓€涓彈鎺х洃鍚櫒锛岃瀹冪殑鍛戒护琛屾樉寮忓寘鍚?`dashboard.server --workspace-root <WORKSPACE_ROOT>`锛屼絾瀵?`GET /api/workbench/hub` 鍙繑鍥?`text/html`銆?
3. 鍏堢‘璁ら鎺㈤拡缁撴灉鏄細
   - `StatusCode = 200`
   - `ContentType = text/html; charset=utf-8`
4. 杩愯锛?

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Launch-Webnovel-Dashboard.ps1 -Port 8877 -NoBrowser
```

5. 鎴愬姛鍙ｅ緞锛?
   - 鍐崇瓥杈撳嚭鍖呭惈 `stale_restart`
   - 鏃ュ織鍖呭惈 `Stop result: stopped PID ...`
   - 闅忓悗 `/api/workbench/hub` 杩斿洖 `application/json`
6. 鑻ユ竻鐞嗗け璐ユ槸 `permission_denied` 鎴栧綋鍓嶇敤鎴锋棤鏉冪粨鏉熸棫杩涚▼锛屽簲褰掔被涓虹幆澧冮棶棰橈紝涓嶅簲鐩存帴鍒や负鍚姩鍣ㄩ€昏緫鍥炲綊銆?

### 璐ㄩ噺椤典綆鏁版嵁 smoke 鍦烘櫙

褰撻渶瑕侀獙璇佽川閲忛〉浣庢暟鎹€佺殑鐪熷疄灞曠ず鏃讹紝浣跨敤 bootstrap 鍚庝笉琛ュ啓杩愯璁板綍鐨勬柊椤圭洰銆?

鎺ㄨ崘姝ラ锛?

1. 閫氳繃 `POST /api/project/bootstrap` 鍒涘缓涓存椂椤圭洰锛屼緥濡傛斁鍦?`webnovel-writer\.tmp-playwright-YYYYMMDD\low-data-smoke-*`銆?
2. 淇濇寔椤圭洰鍙湁 bootstrap 榛樿鏁版嵁锛屼笉棰勫厛鍐欏叆锛?
   - 瀹℃煡鎸囨爣
   - 娓呭崟璇勫垎
   - 妫€绱㈣皟鐢?
   - 宸ュ叿缁熻
3. 鎵撳紑锛?

```powershell
http://127.0.0.1:8765/?project_root=<url-encoded-project-root>&page=quality
```

4. 鎴愬姛鍙ｅ緞锛?
   - 鍑虹幇 `褰撳墠璐ㄩ噺椤典粛澶勪簬浣庢暟鎹€乣
   - 鍑虹幇 `杩樼己灏?4 绫诲叧閿川閲忚褰曪紝褰撳墠瓒嬪娍鍒ゆ柇浼氬亸寮便€俙
   - 鍥涘紶鎽樿鍗￠兘鍑虹幇瀵瑰簲涓枃绌烘€佽鏄?

### 鐫ｅ姙 smoke 澶瑰叿 + 瀹氬悜鐪熷疄宸℃

褰撻渶瑕侀獙璇?`supervisor` 涓?`supervisor-audit` 涓ら〉涓嶅啀鏄€滃叏绌虹洸鍖衡€濇椂锛岀粺涓€浣跨敤浠撳簱鍐呮寮忚剼鏈紝涓嶅啀鐩存帴澶嶇敤 `output/verification` 閲岀殑涓存椂鑴氭湰銆?

姝ｅ紡鍏ュ彛锛?

```powershell
& '.\tools\Tests\Run-Webnovel-ReadonlyAudit.ps1'
```

甯哥敤鍙樹綋锛?

```powershell
& '.\tools\Tests\Run-Webnovel-ReadonlyAudit.ps1' -PreferredPort 8765
& '.\tools\Tests\Run-Webnovel-ReadonlyAudit.ps1' -OutputRoot 'D:\CodexProjects\webnovel writing\output\verification\readonly-audit\manual-run'
& '.\tools\Tests\Run-Webnovel-ReadonlyAudit.ps1' -ProjectRoot 'D:\path\to\existing-supervisor-smoke-project'
```

鑴氭湰鍐呴儴鍥哄畾娴佺▼锛?

1. 閫氳繃 `supervisor_smoke_fixture.py` 鐢熸垚鎴栧鐢ㄧ潱鍔?smoke fixture锛堝啋鐑熷す鍏凤級銆?
2. 閫氳繃 `Start-Webnovel-Writer.ps1` 浠ラ」鐩ā寮忓惎鍔?Dashboard锛堝伐浣滃彴锛夈€?
3. 浼樺厛灏濊瘯 `8765`锛涜嫢绔彛琚崰鐢紝鑷姩鍥為€€鍒?`8876..8895` 鐨勯殧绂荤鍙ｃ€?
4. 鍏堝仛 6 涓?supervisor API锛堟帴鍙ｏ級棰勬锛屽叏閮ㄥ懡涓槇鍊煎悗鎵嶈繘鍏ョ湡瀹為〉闈㈠贰妫€銆?
5. 閫氳繃 Playwright锛堟祻瑙堝櫒鑷姩鍖栵級鎶撳彇 `supervisor` 涓?`supervisor-audit` 涓ら〉鐨勫揩鐓с€佹埅鍥惧拰鎿嶄綔杞綍銆?

鍥哄畾浜х墿锛?

- `fixture-result.json`
- `precheck.json`
- `playwright-transcript.txt`
- `snapshot-index.txt`
- `screenshot-index.txt`
- `result.json`

椤甸潰绾у浐瀹氶獙鏀剁偣锛?

- `supervisor` 椤靛繀椤诲嚭鐜伴潪绌烘椿鍔ㄥ缓璁尯涓庡凡淇濆瓨娓呭崟鍖猴紝涓旀病鏈夐〉绾?`鐫ｅ姙鍙版暟鎹埛鏂板け璐
- `supervisor-audit` 椤电殑鏃堕棿绾裤€佸璁′綋妫€銆佷慨澶嶉婕斻€佷慨澶嶅綊妗ｃ€佹竻鍗曞綊妗ｉ兘涓嶈兘钀藉洖绌烘€侊紝涓旀病鏈夐〉绾?`鐫ｅ姙瀹¤鏁版嵁鍒锋柊澶辫触`
- 椤甸潰鏂囨淇濇寔涓枃浼樺厛锛屼笉搴旀毚闇?`manual-only`銆乣approval-gate`銆乣hard blocking issue`銆乣Detected audit schema`銆乣through v2` 杩欑被鍐呴儴鑻辨枃璇?

澶辫触褰掑洜鍥哄畾浣跨敤 `result.json.classification`锛?

- `fixture_failure`锛氶妫€鏈懡涓槇鍊硷紝鍏堜慨澶瑰叿鎴栨帴鍙ｏ紝涓嶈繘鍏?UI 鍒ゆ柇
- `ui_defect_reproduced`锛氶妫€鍏ㄩ儴鍛戒腑锛屼絾鐪熷疄椤甸潰浠嶆毚闇茬┖鎬併€佸唴閮ㄨ嫳鏂囪瘝鎴栭〉绾ч敊璇?
- `pass`锛氶妫€鍜岀湡瀹為〉闈㈡鏌ュ叏閮ㄩ€氳繃
- `verification_complete_docs_pending`锛氬彧璺戜簡鎺ュ彛棰勬锛岃烦杩囨祻瑙堝櫒楠屾敹锛涗笉鑳戒綔涓烘寮忔斁琛岀粨鏋?

璇︾粏鍙傛暟銆佷骇鐗╄鏄庡拰褰掑洜鍙ｅ緞瑙?`dashboard-readonly-audit.md`銆?

### 鐗堟湰绾?bootstrap -> plan -> write -> review -> readonly audit 楠屾敹

褰撻渶瑕佸垽鏂€滃綋鍓嶅皬璇村啓浣滈」鐩槸鍚﹀凡缁忚揪鍒板彲鎸佺画瀹炵敤鐘舵€佲€濇椂锛岀粺涓€浣跨敤浠撳簱鍐呮寮?`real e2e` 鑴氭湰锛屼笉鍐嶆墜宸ユ嫾涓€杞?API 璋冪敤涓庨〉闈㈠洖褰掋€?

姝ｅ紡鍏ュ彛锛?

```powershell
& '.\tools\Tests\Run-Webnovel-RealE2E.ps1'
```

甯哥敤鍙樹綋锛?

```powershell
& '.\tools\Tests\Run-Webnovel-RealE2E.ps1' -PreferredPort 8765
& '.\tools\Tests\Run-Webnovel-RealE2E.ps1' -OutputRoot 'D:\CodexProjects\webnovel writing\output\verification\real-e2e\manual-run'
& '.\tools\Tests\Run-Webnovel-RealE2E.ps1' -RunId 'manual01'
& '.\tools\Tests\Run-Webnovel-RealE2E.ps1' -ProjectRoot 'D:\path\to\existing-project'
```

鑴氭湰鍐呴儴鍥哄畾娴佺▼锛?

1. 璁板綍 Git锛堢増鏈帶鍒讹級鍒嗘敮/鎻愪氦銆丳ython / Node / Playwright 鍩虹嚎锛屼互鍙?LLM / RAG 鐘舵€併€?
2. 鍒涘缓鎴栧鐢?1 涓湡瀹為」鐩洰褰曘€?
3. 閫氳繃 `POST /api/project/bootstrap` 鍒濆鍖栭」鐩€?
4. 璇诲彇骞朵繚瀛樹竴娆?`Planning Profile`锛岄獙璇佸喎鍚姩璁″垝杈撳叆閾俱€?
5. 鎵ц `plan volume=1`銆?
6. 鎵ц `write chapter=1..3`锛屽湪绔犺妭绠€鎶ュ鎵圭偣鑷姩鎵瑰噯缁х画銆?
7. 鎵ц `review chapter_range=1-3`锛岄獙璇佺粨鏋勫寲 review summary銆?
8. 浠呭湪 review 缁欏嚭鍙慨澶嶅€欓€夋椂瑙﹀彂 1 娆?`repair`銆?
9. 鐢?Playwright 妫€鏌?`control / tasks / quality` 椤甸潰銆?
10. 澶嶇敤鏃㈡湁 readonly audit 鑴氭湰妫€鏌?`supervisor / supervisor-audit`銆?

鍥哄畾浜х墿锛?

- `environment.json`
- `bootstrap-response.json`
- `planning-profile-before.json`
- `planning-profile-after.json`
- `task-summary-plan.json`
- `task-summary-write-ch1.json`
- `task-summary-write-ch2.json`
- `task-summary-write-ch3.json`
- `task-summary-review-1-3.json`
- `task-summary-repair.json`
- `project-state-final.json`
- `readonly-audit-result.json`
- `acceptance-report.md`

澶辫触褰掑洜鍥哄畾浣跨敤鏈€缁?`classification`锛?

- `environment_blocked`
- `mainline_failure`
- `page_regression`
- `readonly_audit_failure`
- `pass`

璇︾粏鍙傛暟銆佹爣鍑嗕骇鐗╁拰楠屾敹鍙ｅ緞瑙?`dashboard-real-e2e.md`銆?
### 澶氬瓙浠ｇ悊娴嬭瘯鍗忚皟鍣紙浠撳簱绾ч獙璇佸叆鍙ｏ級

褰撲綘闇€瑕佽窇鈥滄湰鍦颁笁 lane 骞惰 + 鍗曚富閾?RealE2E 涓茶鈥濈殑浠撳簱绾ч獙璇佹椂锛屼娇鐢ㄦ柊鐨勫崗璋冨櫒鑴氭湰銆傚畠涓嶆槸浜у搧鍔熻兘鍙樻洿锛岃€屾槸鎶?backend銆乨ata-cli銆乫rontend 涓変釜鏈湴楠岃瘉 lane 鍏堝苟琛岃窇瀹岋紝鍐嶅湪娌℃湁 `local blocker`锛堟湰鍦伴樆鏂級鍜?`environment blocker`锛堢幆澧冮樆鏂級鏃跺鐢ㄧ幇鏈?RealE2E 閫昏緫銆?
姝ｅ紡鍏ュ彛锛?
```powershell
& '.\tools\Tests\Run-Webnovel-MultiAgentTest.ps1'
```

娴佺▼鎽樿锛?
1. 鍏堝仛 `preflight`锛堥妫€锛夛紝妫€鏌?`python`銆乣node`銆乣npx`銆丳laywright锛堟祻瑙堝櫒鑷姩鍖栵級鑴氭湰璺緞浠ュ強 RealE2E 妯″潡璺緞銆?2. 骞惰璺?`backend`銆乣data-cli`銆乣frontend` 涓変釜鏈湴 lane銆?3. `backend` lane 鍏堝湪浠撳簱鏍规墽琛?`python -m pytest webnovel-writer\webnovel-writer\dashboard\tests\test_app.py -q`锛屽啀鍦?`webnovel-writer\webnovel-writer` 鎵ц `python -m pytest dashboard\tests\test_app.py dashboard\tests\test_orchestrator.py dashboard\tests\test_task_store.py -q`銆?4. `data-cli` lane 鍦?`PYTHONPATH=<appRoot>\scripts` 涓嬩緷娆℃墽琛?`python -m pytest scripts\data_modules\tests\test_state_file.py scripts\data_modules\tests\test_state_manager_extra.py scripts\data_modules\tests\test_sql_state_manager.py scripts\data_modules\tests\test_webnovel_unified_cli.py -q` 鍜?`python -m pytest scripts\data_modules\tests\test_webnovel_cli_e2e_mock.py -q`銆?5. `frontend` lane 鍦?`webnovel-writer\webnovel-writer\dashboard\frontend` 鎵ц `npm test` 鍜?`npm run typecheck`銆?6. 鍙湁褰撴湰鍦?lanes 娌℃湁褰㈡垚 `local blocker` 涓旈妫€娌℃湁 `environment blocker` 鏃讹紝鎵嶄細缁х画璋冪敤鐜版湁 `tools\Webnovel-RealE2E.psm1` / `tools\Tests\Run-Webnovel-RealE2E.ps1` 鐨?RealE2E 涓婚摼銆?
榛樿浜х墿鏍圭洰褰曪細

```text
output/verification/multi-agent-test/YYYYMMDD-runid/
```

Dashboard verification console（验证控制台）：

- 入口在 Dashboard 工作台的 `验证页`，不绑定单个项目。
- 页面会直接调用正式脚本 `tools\Tests\Run-Webnovel-MultiAgentTest.ps1`，不会绕过协调器自己拼测试步骤。
- 页面会展示 `active_execution`（活动运行）、最近 10 次 runs（运行记录）、`classification`（分类）、`next_action`（动作码）、`failure_summary`（失败摘要）、`minimal_repro`（最小复现）、`failure_fingerprint`（失败指纹）、`RealE2E` 状态以及报告/日志入口。
- 活动运行会把状态落盘到 `output/verification/multi-agent-test/_runtime/active-execution.json` 与 `_runtime/last-known.json`；Dashboard 重启后会结合 PID（进程号）存活检查和 `result.json` / `progress.json` 做恢复。
- 活动运行时前端会高频轮询 `GET /api/workbench/verification/runs/{run_id}/progress`，展示 `phase / current_lane / current_step / completed_steps / total_steps / updated_at`。
- Dashboard 只允许读取当前 run 目录里的 `report.md`、console stdout/stderr 和 step 级 stdout/stderr/combined log，不开放任意文件浏览；日志接口默认使用 `tail_lines` 截尾返回，避免大日志拖慢页面。
- 页面支持 `POST /api/workbench/verification/run/stop` 停止当前 active run，以及 `POST /api/workbench/verification/runs/{run_id}/rerun` 基于旧 run 创建新 run。
- 同一 workspace（工作区）同一时刻只允许一个 active multi-agent test（活动多子代理验证）；若已存在运行中任务，再次启动会得到 `VERIFICATION_ALREADY_RUNNING`。

鍥哄畾浜х墿锛?
- `preflight.json`
- `backend-lane.json`
- `data-cli-lane.json`
- `frontend-lane.json`
- `real-e2e-result.json`
- `result.json`
- `report.md`

闄勫姞鐩綍锛?
- `lane-logs/`
- `real-e2e/`

鏇村缁嗚妭瑙?`docs/multi-agent-test.md`。

Addendum (2026-03-25):

- The coordinator no longer uses the old rule of "more than one failed step in a lane means local blocker".
- `preflight` now records both static existence checks and lightweight availability probes in `checks[]`, `missing_paths[]`, and `failed_commands[]`.
- Every step now records `blocking_severity`, `timeout_seconds`, and separate stdout/stderr/combined log paths.
- `failure_kind` is now a first-class field with the fixed values `timeout`, `environment`, `test_failure`, and `tooling_failure`.
- Top-level `result.json` now includes `blocking_step_ids[]`, `next_action`, and `failure_summary` for direct triage.

Addendum (2026-03-26):

- Coordinator runs now persist `progress.json`, `control.json`, and `manifest.json` in each run directory.
- `manifest.json` carries `manifest_version`, `run_id`, `classification`, `next_action`, `failure_fingerprint`, and artifact path pointers for Dashboard plus future headless automation.
- Stop requests are cooperative first: Dashboard writes `control.json` and only force-kills after 10 seconds if the coordinator still has not exited.
- `classification = cancelled` now maps to `next_action = rerun_after_cancel`.
- History APIs can now group repeated failures by `failure_fingerprint`, which is derived from missing environment items, `step_id + failure_kind`, or the first failing RealE2E page/task.

## 甯哥敤鐜鍙橀噺

```powershell
$env:WORKSPACE_ROOT = if ($env:WORKSPACE_ROOT) { $env:WORKSPACE_ROOT } else { (Get-Location).Path }
$env:PLUGIN_ROOT = "D:\path\to\webnovel-writer"
$env:SCRIPTS_DIR = Join-Path $env:PLUGIN_ROOT "scripts"
$env:PROJECT_ROOT = python (Join-Path $env:SCRIPTS_DIR "webnovel.py") --project-root $env:WORKSPACE_ROOT where
```

## 甯哥敤杩愮淮鍛戒护

### 绱㈠紩妫€鏌?

```powershell
python (Join-Path $env:SCRIPTS_DIR "webnovel.py") --project-root $env:PROJECT_ROOT index stats
```

### 鐘舵€佹姤鍛?

```powershell
python (Join-Path $env:SCRIPTS_DIR "webnovel.py") --project-root $env:PROJECT_ROOT status -- --focus all
python (Join-Path $env:SCRIPTS_DIR "webnovel.py") --project-root $env:PROJECT_ROOT status -- --focus urgency
```

### RAG 妫€鏌?

```powershell
python (Join-Path $env:SCRIPTS_DIR "webnovel.py") --project-root $env:PROJECT_ROOT rag stats
```

### 娴嬭瘯鍏ュ彛

```powershell
pwsh (Join-Path $env:PLUGIN_ROOT "scripts/run_tests.ps1") -Mode smoke
pwsh (Join-Path $env:PLUGIN_ROOT "scripts/run_tests.ps1") -Mode full
```

### 寮€鍙戜緷璧栧墠缃?

鍦ㄧ洿鎺ヨ繍琛?`pytest`銆佹墦鍖呮垨鍓嶇闈欐€佹鏌ヤ箣鍓嶏紝鍏堝畨瑁呭紑鍙戜緷璧栵細

```powershell
python -m pip install -e "$($env:PLUGIN_ROOT)[dev,dashboard]"
Set-Location (Join-Path $env:PLUGIN_ROOT "dashboard/frontend")
npm install
```

璇存槑锛?

- `pytest-cov` 灞炰簬 Python 娴嬭瘯鍓嶇疆渚濊禆锛涘鏋滄湭瀹夎锛屼粨搴撴牴鐨?`pytest` 閰嶇疆浼氬洜瑕嗙洊鐜囧弬鏁扮己澶辫€屽け璐ャ€?
- `npm run lint`銆乣npm run typecheck`銆乣npm run test:*` 閮戒緷璧栧墠绔湰鍦?`node_modules/`銆?

## Dashboard Frontend Artifact Maintenance

`dashboard/frontend/dist/` is the runtime static asset directory for the dashboard and remains committed in this project.

Rules:

- If `dashboard/frontend/src/` changes, run `npm run build` and commit the resulting `dist/` update in the same change.
- `dist/index.html` and `dist/assets/` must come from the same build output.
- Remove superseded hashed files from `dist/assets/` when a new build replaces them.

## Runtime State File Discipline

`.webnovel/state.json` is a shared runtime file for dashboard and orchestration flows.

Rules:

- Read and write it through the shared state access layer in `scripts/data_modules/state_file.py`.
- Runtime writes must follow `FileLock` + lock-in reread + incremental mutation + atomic write.
- Do not add new direct `read_text()/write_text()` mutation paths for `.webnovel/state.json`.

## Cold-Start Planning Operations

Bootstrap and first-run planning now follow a fixed minimum-input contract.

Rules:

- `POST /api/project/bootstrap` must seed both `.webnovel/planning-profile.json` and a usable `澶х翰/鎬荤翰.md` skeleton.
- The recommended first manual action after bootstrap is to open `Planning Profile`, confirm the generated fields, and save once before running `plan`.
- `plan` preflight merges inputs in this order: `.webnovel/planning-profile.json` -> `.webnovel/state.json` `planning.project_info` -> `澶х翰/鎬荤翰.md`.
- If required planning inputs are still missing, `plan` must fail with `PLAN_INPUT_BLOCKED` and include `details.blocking_items`.
- When `PLAN_INPUT_BLOCKED` is returned, do not expect `澶х翰/volume-01-plan.md` or `planning.volume_plans[1]` to be updated.

## Invalid Step Output Recovery

Dashboard mainline tasks now standardize `INVALID_STEP_OUTPUT` semantics instead of treating all parse failures as the same terminal error.

Rules:

- `INVALID_STEP_OUTPUT` must preserve the original error code and expose structured `details`.
- `details` must include:
  - `parse_stage`
  - `raw_output_present`
  - `missing_required_keys`
  - `recoverability`
  - `suggested_resume_step`
- `recoverability` is constrained to:
  - `auto_retried`: the orchestrator has already scheduled the one allowed automatic retry for this step.
  - `retriable`: the step was not auto-retried, but the failure is still safe to retry manually.
  - `terminal`: the step has exhausted automatic recovery for this failure class.
- Automatic retry is enabled once for:
  - `plan.plan`
  - `repair.repair-draft`
  - `repair.consistency-review`
  - `repair.continuity-review`
  - `write.context`
  - `write.draft`
  - `write.polish`
  - `write.consistency-review`
  - `write.continuity-review`
  - `write.ooc-review`
  - `review.consistency-review`
  - `review.continuity-review`
  - `review.ooc-review`
- `data-sync` remains excluded from automatic retry in this phase; if it fails with `INVALID_STEP_OUTPUT`, it should surface as `retriable` with `suggested_resume_step = data-sync`.

## Repair Task

Dashboard now supports a dedicated chapter-level `repair` task instead of folding automatic rewrite into `review`.

Rules:

- Launch path: `POST /api/tasks/repair`
- Default behavior: direct writeback after task launch, unless the request explicitly sets `require_manual_approval = true`
- Workflow: `repair-plan -> repair-draft -> consistency-review -> continuity-review -> review-summary -> approval-gate -> repair-writeback`
- Automatic writeback is allowed only when:
  - the issue type is in the repair whitelist
  - repair review is not blocking
  - the task has either passed `approval-gate` or does not require manual approval
  - a chapter backup is written before overwrite
- If `require_manual_approval = true`, the task must pause at `approval-gate` with `status = awaiting_writeback_approval` before overwrite.
- If repair review still blocks the chapter, the task must fail with `REPAIR_REVIEW_BLOCKED` and must not overwrite the chapter body.

## Local Test Entrypoints

Use PowerShell-compatible commands only.

Backend:

```powershell
Set-Location "D:\CodexProjects\webnovel writing"
python -m pytest webnovel-writer\webnovel-writer\dashboard\tests\test_app.py -q

Set-Location "D:\CodexProjects\webnovel writing\webnovel-writer\webnovel-writer"
python -m pytest dashboard\tests\test_app.py dashboard\tests\test_orchestrator.py dashboard\tests\test_task_store.py -q
$env:PYTHONPATH='D:\CodexProjects\webnovel writing\webnovel-writer\webnovel-writer\scripts'
python -m pytest scripts\data_modules\tests\test_state_file.py scripts\data_modules\tests\test_state_manager_extra.py scripts\data_modules\tests\test_sql_state_manager.py scripts\data_modules\tests\test_webnovel_unified_cli.py -q
python -m pytest scripts\data_modules\tests\test_webnovel_cli_e2e_mock.py -q
```

Frontend:

```powershell
Set-Location "D:\CodexProjects\webnovel writing\webnovel-writer\webnovel-writer\dashboard\frontend"
npm test
npm run typecheck
npm run build
```

Rules:

- Keep `npm test` as the single frontend entrypoint for day-to-day verification.
- `npm run test:state` is reserved for `node:test` logic files.
- `npm run test:ui` is reserved for Vitest files and now includes the previously omitted suites.
- `scripts\data_modules\tests\*` must run with `PYTHONPATH` pointed at `webnovel-writer\webnovel-writer\scripts`; otherwise import-path failures count as invalid verification, not product regressions.
- `dashboard/frontend/dist/` remains committed; when runtime source files change, rebuild and commit the matching `dist/` update in the same change.
- If a change touches `supervisor` / `supervisor-audit` or task-resume semantics, run `& '.\tools\Tests\Run-Webnovel-ReadonlyAudit.ps1'` before release.
- If a change touches `bootstrap` input contracts or the `plan / write / review / repair` mainline, run `& '.\tools\Tests\Run-Webnovel-RealE2E.ps1'` before release.

## LLM fallback锛堟ā鍨嬭嚜鍔ㄩ檷绾э級

褰?`WEBNOVEL_LLM_PROVIDER=openai-compatible` 涓旈粯璁ゆā鍨嬩负 `gpt-5.4` 鏃讹紝`write -> draft` 涓?`write -> polish` 鐜板湪鏀寔鑷姩闄嶇骇锛坒allback锛夌瓥鐣ャ€?
- 鍏堟墽琛岀幇鏈夊悓妯￠噸璇曪紙same-model retry锛夛紝涓嶆敼 `WEBNOVEL_LLM_MAX_RETRIES`
- 浠呭綋鏈€缁堥敊璇睘浜?`LLM_TIMEOUT` 鎴栧彲閲嶈瘯 `5xx` 鐨?`LLM_HTTP_ERROR` 鏃讹紝鎵嶄細鍒囧埌鍥為€€妯″瀷
- 榛樿鍥為€€妯″瀷鏄?`gpt-5.4-mini`
- `4xx`銆侀厤缃敊璇€佽В鏋愰敊璇€乣INVALID_STEP_OUTPUT` 閮戒笉浼氳Е鍙戣嚜鍔ㄩ檷绾?
鐩稿叧鐜鍙橀噺锛?
```text
WEBNOVEL_LLM_ENABLE_FALLBACK=true
WEBNOVEL_LLM_FALLBACK_MODEL=gpt-5.4-mini
WEBNOVEL_LLM_FALLBACK_STEPS=draft,polish
WEBNOVEL_LLM_FALLBACK_ON=LLM_TIMEOUT,LLM_HTTP_ERROR
```

鎺掓煡鏃朵紭鍏堟煡鐪?`.webnovel/observability/llm-runs/<task-step>/`锛?
- `request.json`锛氫富妯″瀷 / 鍥為€€妯″瀷涓庤秴鏃堕绠?- `raw-output*.meta.json`锛氭瘡娆?attempt锛堝皾璇曪級鐨勫疄闄呮ā鍨嬨€佽Е鍙戦敊璇€丠TTP 鐘舵€?- `result.json` / `error.json`锛氭渶缁?`effective_model`銆乣fallback_used`銆乣fallback_exhausted`


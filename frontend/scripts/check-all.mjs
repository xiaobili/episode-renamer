// 一次跑齐所有前端机械判据（就是 scripts/ 下的那五个 check-*.mjs）。
//
// 为什么需要它：本计划自查出的三个缺陷**全部**是同一形态 ——
//   · 断言抓不到真实的错误实现（零鉴别力）；
//   · 检查本身不可能失败（比如 adapter resolve 一个 401，被 axios 当成成功）；
//   · 写了但**从来没有人跑**。
// 前两个靠断言设计，第三个只能靠「有一条命令，跑它就等于全跑」。故这里把五个脚本
// 串起来，任一失败即非零退出 —— 它保证的正是「它们确实被执行了」。
//
// 名单**硬编码**，不 glob：一是 glob 会把 check-all.mjs 自己卷进来（递归），
// 二是脚本被改名/删除时硬编码的名单会**报错**，而 glob 会静默少跑一个 ——
// 「静默少跑」正是这个 runner 要防的东西。
//
// 零依赖：只用 node 内置模块（与其余 check-*.mjs 同规格）。
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const HERE = new URL('.', import.meta.url)
const SCRIPTS = [
  'check-settings-schema.mjs',
  'check-scrape-gate.mjs',
  'check-rename-payload.mjs',
  'check-sfc-compile.mjs',
  'check-workspace-gating.mjs',
]

let failed = 0
for (const name of SCRIPTS) {
  const path = fileURLToPath(new URL(name, HERE))
  // 名单里的脚本必须真的存在：不存在也**算失败**，否则删掉一个脚本会让 runner 变绿。
  if (!existsSync(path)) {
    failed += 1
    console.log(`\n=== ${name} ===\nFAIL 脚本不存在：${path}`)
    continue
  }
  console.log(`\n=== ${name} ===`)
  // stdio: 'inherit' 让每个脚本自己的 PASS/FAIL 直接出现在终端上 —— 汇总行不能
  // 替代明细：出错时要能一眼看到是哪一条断言红的。
  const res = spawnSync(process.execPath, [path], { cwd: fileURLToPath(new URL('..', HERE)), stdio: 'inherit' })
  // 信号杀死 / 非零退出都算失败。spawnSync 的 error（如 node 起不来）同样归零。
  if (res.error || res.status !== 0) {
    failed += 1
    console.log(`!!! ${name} 失败（status=${res.status ?? 'null'}${res.error ? `, ${res.error.message}` : ''}）`)
  }
}

console.log(
  failed === 0
    ? `\n全部 ${SCRIPTS.length} 个检查脚本通过`
    : `\n${failed}/${SCRIPTS.length} 个检查脚本失败`,
)
process.exit(failed === 0 ? 0 : 1)

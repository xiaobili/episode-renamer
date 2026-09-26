// 编译校验：把 src/ 下每个 .vue 都过一遍 vue/compiler-sfc。
//
// 为什么需要它：Vite 只打包从入口**可达**的模块。未被 import 的组件不在模块图里，
// 因此 `npm run build` 通过**不能证明**它能编译 —— 一个尚未接线的组件里若有语法
// 错误、模板里引用了不存在的指令、或 <script setup> 里调用了未定义的函数，构建
// 不会报任何错；要到它第一次被 import 时才炸。
//
// 本项目第一期会先建好六个 UI 原语而**刻意不接线**（第二、三期才逐个换上去），
// 所以这个盲区会持续数期。每一次「新建了组件但还没有调用方」之后都应该跑一次。
//
// 第二条盲区（模板里用了却没 import 的组件）在 2026-09-26 那轮补上：光调
// compileScript + compileTemplate 是抓不到的 —— 那种组件会编译成
// `_resolveComponent("X")`，是**运行期**去全局注册里找，编译期一声不吭，
// Rollup 也不吭声（本仓库实测：把一个组件的 import 删掉，构建照样成功）。
// 现在的做法是把 <script setup> 的 bindingMetadata 喂给模板编译器：已 import 的
// 组件会被直接引用，只有没绑定的才会退化成 _resolveComponent —— 于是「剩下的
// _resolveComponent」就成了一个可判定的信号，下面逐条报出来。
//
// 仍然**没有**覆盖的：普通 .js 文件里漏掉的函数 import（运行期 ReferenceError，
// Rollup 同样静默）。本脚本只看 .vue，这一条留给将来。
//
// 用法：cd frontend && node scripts/check-sfc-compile.mjs
// 退出码非 0 表示有文件编译失败，失败清单打印在 stdout。

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { parse, compileScript, compileTemplate } from 'vue/compiler-sfc'

const SRC = 'src'

// vue-router 通过 app.use(router) 注册的全局组件（见 src/main.js）。它们不出现在
// 任何 SFC 的 import 列表里, 也不该出现 —— 所以必须白名单, 否则本检查会对
// App.vue 的 <router-view> 和 AppTopBar 的 <RouterLink> 误报。
// 比较用 camelize 后的小写形式, 与编译器的查找方式对齐（kebab 与 Pascal 都认）。
const GLOBAL_COMPONENTS = new Set(['routerlink', 'routerview'])

const UNRESOLVED_COMPONENT = /resolveComponent\(\s*["']([^"']+)["']/g

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return walk(path)
    return path.endsWith('.vue') ? [path] : []
  })
}

let failed = 0

for (const file of walk(SRC)) {
  const source = readFileSync(file, 'utf8')
  const { descriptor, errors } = parse(source, { filename: file })
  const problems = [...errors]

  try {
    let bindings
    if (descriptor.scriptSetup || descriptor.script) {
      bindings = compileScript(descriptor, { id: file }).bindings
    }
    if (descriptor.template) {
      const result = compileTemplate({
        source: descriptor.template.content,
        filename: file,
        id: file,
        // 不传 bindingMetadata 的话, 模板里**每一个**组件都会被编译成
        // _resolveComponent("X") —— 「模板里用了却没 import」与「一切都好」
        // 产出的代码长得一样, 于是无从判定。传了之后, 已绑定的组件被直接引用,
        // 剩下的 _resolveComponent 就是缺 import 的那一个。
        compilerOptions: { bindingMetadata: bindings },
      })
      problems.push(...result.errors)
      for (const match of result.code.matchAll(UNRESOLVED_COMPONENT)) {
        const name = match[1]
        // kebab 与 Pascal 都认: App.vue 写的是 <router-view>, AppTopBar 写的是
        // <RouterLink> —— 两个都来自 app.use(router), 不在任何 import 列表里。
        if (GLOBAL_COMPONENTS.has(name.replace(/-/g, '').toLowerCase())) continue
        problems.push(
          `模板里的 <${name}> 没有对应的 import/绑定: 编译产物退化成 ` +
            `_resolveComponent("${name}")，那是运行期去全局注册里找 —— ` +
            '编译期与 Rollup 都不会报错，找不到就是控制台警告加一片空白。',
        )
      }
    }
  } catch (error) {
    problems.push(error)
  }

  if (problems.length) {
    failed += 1
    console.log('FAIL', file)
    for (const problem of problems) {
      console.log('    ', String(problem).split('\n')[0])
    }
  } else {
    console.log('OK  ', file)
  }
}

console.log(failed === 0 ? '\n全部 SFC 可编译' : `\n${failed} 个文件编译失败`)
process.exitCode = failed === 0 ? 0 : 1

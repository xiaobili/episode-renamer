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
// 用法：cd frontend && node scripts/check-sfc-compile.mjs
// 退出码非 0 表示有文件编译失败，失败清单打印在 stdout。

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { parse, compileScript, compileTemplate } from 'vue/compiler-sfc'

const SRC = 'src'

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
    if (descriptor.scriptSetup || descriptor.script) {
      compileScript(descriptor, { id: file })
    }
    if (descriptor.template) {
      const result = compileTemplate({
        source: descriptor.template.content,
        filename: file,
        id: file,
      })
      problems.push(...result.errors)
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

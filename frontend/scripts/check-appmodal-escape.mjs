// AppModal 的 Escape「分两拍」判据 —— 纯源码判据，不需要浏览器。
//
// 为什么需要它：Escape 那条 bug 只会在真实按键下现形。当时对话框里的搜索框
// 写了 `stopPropagation()` + `preventDefault()`，看起来完全正确，源码级断言
// 也全绿，但实际按 Esc 仍然直接关窗。根因是 AppModal 的监听器挂在 document 的
// **capture** 阶段：捕获阶段早于目标元素上的任何冒泡监听器，内部的阻止动作
// 根本来不及生效（浏览器实测监听顺序恒为 doc-capture → target → 冒泡）。
//
// 所以这里钉住三件事，三件缺一都会退回那个 bug：
//   1. 捕获拍遇到「焦点在面板内」时必须**不关窗**（让位）；
//   2. 冒泡拍必须存在，否则让位之后没人再关窗，对话框关不掉；
//   3. 两拍都必须走同一个函数体，靠标志位分派 —— 它是唯一能保证两拍语义不漂移
//      的写法，拆成两份函数迟早改漏一处。
//
// 运行：node scripts/check-appmodal-escape.mjs

import { readFileSync } from 'node:fs'

const SRC = new URL('../src/components/ui/AppModal.vue', import.meta.url)
const source = readFileSync(SRC, 'utf8')

let failed = 0

function ok(label, pass, detail = '') {
  if (pass) {
    console.log('PASS', label)
  } else {
    failed += 1
    console.log('FAIL', label, detail)
  }
}

/** 取 <script setup> 的内容（模板里也可能出现 addEventListener 字样，不取模板）。 */
function scriptBody(src) {
  const match = src.match(/<script setup>([\s\S]*?)<\/script>/)
  return match ? match[1] : ''
}

const script = scriptBody(source)
ok('能取到 <script setup>', script.length > 0)

/** 取某个函数的函数体（按大括号配平，避免正则吃到下一个函数）。 */
function fnBody(name) {
  const start = script.indexOf(`function ${name}(`)
  if (start < 0) return ''
  const open = script.indexOf('{', start)
  if (open < 0) return ''
  let depth = 0
  for (let i = open; i < script.length; i += 1) {
    const ch = script[i]
    if (ch === '{') depth += 1
    else if (ch === '}') {
      depth -= 1
      if (depth === 0) return script.slice(open + 1, i)
    }
  }
  return ''
}

// --- 1. 捕获拍：焦点在面板内时不关窗 ---
{
  const body = fnBody('onKeydown')
  ok('onKeydown 存在', body.length > 0)
  ok(
    '捕获拍遇到面板内焦点时让位（不 close）',
    /capturePass\s*&&[\s\S]{0,120}contains\(document\.activeElement\)[\s\S]{0,40}return/.test(body),
    body.slice(0, 200),
  )
}

// --- 2. 冒泡拍真的注册了，且与捕获拍分开 ---
{
  ok(
    'capture 监听注册存在',
    /addEventListener\(\s*'keydown'\s*,\s*onCaptureKeydown\s*,\s*true\s*\)/.test(script),
  )
  ok(
    '冒泡监听注册存在（没有它，让位之后 Esc 关不掉窗）',
    /addEventListener\(\s*'keydown'\s*,\s*onBubbleKeydown\s*\)/.test(script),
  )
  // 移除必须**按函数体分别核对**，不能用 includes 查全文件：onClose 与
  // onBeforeUnmount 各有一份移除语句，查全文件时删掉其中一处仍然命中另一处 ——
  // 变异测试里就是这样漏过了一次（M4 变异后断言仍全绿）。
  const closeBody = fnBody('onClose')
  ok('onClose 移除 capture 监听', /removeEventListener\(\s*'keydown'\s*,\s*onCaptureKeydown\s*,\s*true\s*\)/.test(closeBody))
  ok(
    'onClose 移除冒泡监听（否则对话框关闭后仍在关别人的窗）',
    /removeEventListener\(\s*'keydown'\s*,\s*onBubbleKeydown\s*\)/.test(closeBody),
  )
  ok('onBeforeUnmount 中也有移除（模态在打开状态下被卸载的路径）',
    /onBeforeUnmount\([\s\S]{0,400}removeEventListener\(\s*'keydown'\s*,\s*onCaptureKeydown\s*,\s*true\s*\)/.test(script)
      && /onBeforeUnmount\([\s\S]{0,400}removeEventListener\(\s*'keydown'\s*,\s*onBubbleKeydown\s*\)/.test(script))
}

// --- 3. 两拍共用一个函数体 ---
{
  const capture = fnBody('onCaptureKeydown')
  const bubble = fnBody('onBubbleKeydown')
  ok('捕获拍置标志位并调用 onKeydown', /capturePass\s*=\s*true/.test(capture) && capture.includes('onKeydown(event)'))
  ok('捕获拍在 finally 里复位标志位（抛错也不会卡在「捕获」语义上）', /finally[\s\S]{0,60}capturePass\s*=\s*false/.test(capture))
  ok('冒泡拍清标志位并调用 onKeydown', /capturePass\s*=\s*false/.test(bubble) && bubble.includes('onKeydown(event)'))
}

// --- 4. 冒泡拍必须尊重「控件已经消费了这次 Escape」 ---
// 少了这条，搜索框的 preventDefault 等于白写：捕获拍让位了，冒泡拍照样关窗。
{
  const body = fnBody('onKeydown')
  ok(
    '冒泡拍检查 defaultPrevented',
    /defaultPrevented[\s\S]{0,40}return/.test(body),
  )
}

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1

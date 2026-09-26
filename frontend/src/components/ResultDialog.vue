<template>
  <AppModal
    :model-value="modelValue"
    title="重命名结果"
    z-index="50"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="flex max-h-[85vh] w-full max-w-[700px] flex-col overflow-hidden rounded-[12px] bg-surface shadow-overlay">
      <div class="flex shrink-0 items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <h2 class="text-[14px] font-semibold text-ink">重命名结果</h2>
        <button
          type="button"
          aria-label="关闭"
          class="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-2 transition-colors duration-150 hover:bg-sunken hover:text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none"
          @click="$emit('update:modelValue', false)"
        >
          <X class="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto p-5">
        <template v-if="result">
          <div class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div class="rounded-[8px] bg-sunken p-3 text-center">
              <div class="text-[11px] text-ink-3">数据源</div>
              <div class="mt-1 text-[13px] font-semibold text-ink">{{ result.source }}</div>
            </div>
            <div class="rounded-[8px] bg-sunken p-3 text-center">
              <div class="text-[11px] text-ink-3">成功</div>
              <div class="mt-1 text-[13px] font-semibold tabular-nums text-ink">{{ result.executed }}</div>
            </div>
            <div class="rounded-[8px] bg-sunken p-3 text-center">
              <div class="text-[11px] text-ink-3">跳过</div>
              <div class="mt-1 text-[13px] font-semibold tabular-nums text-ink">{{ result.skipped }}</div>
            </div>
            <div
              class="rounded-[8px] p-3 text-center"
              :class="result.failed ? 'bg-danger-soft' : 'bg-sunken'"
            >
              <div class="text-[11px]" :class="result.failed ? 'text-danger' : 'text-ink-3'">失败</div>
              <div
                class="mt-1 text-[13px] font-semibold tabular-nums"
                :class="result.failed ? 'text-danger' : 'text-ink'"
              >{{ result.failed }}</div>
            </div>
          </div>

          <!-- NFO 汇总。只在真有 NFO 动作时出现：覆盖默认关闭, 所以「跳过」是
               常态而非异常 —— 只报「成功 N 个」会让用户以为 NFO 写了, 其实可能
               一个都没写。原因必须跟着数字一起给, 否则用户看到「跳过 50 项」
               也不知道该去勾「覆盖已存在的 NFO」。
               单位有意分两种：「写入 / 跟随移动」是**文件数**（一个落点一件），
               「跳过」是**条目数** —— 同一个目标 NFO 上「生成没写」与「跟随没搬成」
               是两件事，`nfo_skipped` 各出一条（两条理由串也各说各的），计「个」
               会把条目数读成文件数。故顶行用「项」，下面按理由分组同样按条目计，
               顶行才与分项之和对得上。改回「个」前先读 R89。 -->
          <div v-if="nfoStats" class="mb-4 rounded-[8px] bg-sunken px-3 py-2.5 text-[12px]">
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span class="font-semibold text-ink">NFO</span>
              <span v-if="nfoStats.writtenCount" class="tabular-nums text-ink-2">
                {{ nfoStats.dryRun ? '将写入' : '写入' }} {{ nfoStats.writtenCount }} 个
              </span>
              <span v-if="nfoStats.skippedCount" class="tabular-nums text-ink-2">
                {{ nfoStats.dryRun ? '将跳过' : '跳过' }} {{ nfoStats.skippedCount }} 项
              </span>
              <!-- 跟随移动单独一行: 这些文件**不是本程序生成的**, 是重命名时一并
                   搬走的既有 NFO（spec §9.1.1）。算进「写入 N 个」会把用户自己的
                   元数据谎报成生成结果。 -->
              <span v-if="nfoStats.carriedCount" class="tabular-nums text-ink-2">
                {{ nfoStats.dryRun ? '将跟随移动' : '跟随移动' }} {{ nfoStats.carriedCount }} 个
              </span>
            </div>
            <p v-if="nfoStats.reasonText" class="mt-1.5 text-[11px] leading-relaxed text-ink-3">
              跳过原因：{{ nfoStats.reasonText }}
            </p>
            <p v-if="nfoStats.hint" class="mt-1 text-[11px] leading-relaxed text-warn">
              {{ nfoStats.hint }}
            </p>
            <!-- 落点清单: spec §9.4 的可见性要求「显式列出」落点路径。
                 计数与原因分组回答的是「为什么跳过」, 「要写到哪里」只有路径能回答
                 —— 上溯过头时 tvshow.nfo 会落到**库根**而不是剧目录, 而本对话框
                 此前只报数字, 用户在干跑时看不到任何一条落点（干跑的全部意义就是
                 执行前看一眼这个清单）。break-all 让长路径换行而非被截断: 截断
                 等于把这件事又藏回去。 -->
            <ul
              v-if="nfoStats.writtenPaths.length"
              class="mt-1.5 max-h-[132px] space-y-0.5 overflow-y-auto rounded-[6px] border border-line px-2 py-1.5"
            >
              <li class="text-[11px] text-ink-3">
                {{ nfoStats.dryRun ? '计划写入的落点' : '已写入的落点' }}
              </li>
              <li
                v-for="path in nfoStats.writtenPaths"
                :key="path"
                class="break-all font-mono text-[11px] leading-relaxed text-ink-2"
              >
                {{ path }}
              </li>
            </ul>
            <!-- 跟随移动的落点也要列出来（§9.4 的可见性同样适用）: 「跟随移动 2 个」
                 说不出搬到了哪里, 而搬到哪里正是用户要核对的事 -->
            <ul
              v-if="nfoStats.carriedPaths.length"
              class="mt-1.5 max-h-[132px] space-y-0.5 overflow-y-auto rounded-[6px] border border-line px-2 py-1.5"
            >
              <li class="text-[11px] text-ink-3">
                {{ nfoStats.dryRun ? '计划跟随移动的既有 NFO' : '已跟随移动的既有 NFO' }}
              </li>
              <li
                v-for="path in nfoStats.carriedPaths"
                :key="path"
                class="break-all font-mono text-[11px] leading-relaxed text-ink-2"
              >
                {{ path }}
              </li>
            </ul>
          </div>

          <table v-if="result.results?.length" class="w-full text-[12px]">
            <thead class="bg-sunken">
              <tr class="text-ink-2">
                <th class="px-3 py-2 text-left font-semibold">原文件名</th>
                <th class="px-3 py-2 text-left font-semibold">新文件名</th>
                <th class="w-[100px] px-3 py-2 text-left font-semibold">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in result.results" :key="i" class="border-t border-line">
                <td class="max-w-[220px] truncate px-3 py-2 text-ink">{{ r.original_filename }}</td>
                <td class="max-w-[220px] truncate px-3 py-2 text-ink">{{ r.new_filename }}</td>
                <td class="px-3 py-2">
                  <AppBadge :tone="r.success ? 'neutral' : 'danger'">
                    <template #icon>
                      <AlertTriangle v-if="!r.success" class="h-3.5 w-3.5" aria-hidden="true" />
                      <Check v-else class="h-3.5 w-3.5" aria-hidden="true" />
                    </template>
                    {{ r.status }}
                  </AppBadge>
                </td>
              </tr>
            </tbody>
          </table>
        </template>
      </div>

      <div class="flex shrink-0 justify-end border-t border-line px-5 py-3">
        <AppButton variant="secondary" @click="$emit('update:modelValue', false)">关闭</AppButton>
      </div>
    </div>
  </AppModal>
</template>

<script setup>
import { computed } from 'vue'
import { AlertTriangle, Check, X } from 'lucide-vue-next'

import AppModal from './ui/AppModal.vue'
import AppButton from './ui/AppButton.vue'
import AppBadge from './ui/AppBadge.vue'

const props = defineProps({
  modelValue: Boolean,
  result: { type: Object, default: null },
})
defineEmits(['update:modelValue'])

// 跳过的原因是用户唯一能据以行动的线索: 「已存在」→ 去勾「覆盖已存在的 NFO」,
// 「TMDB 未匹配」→ 去补 TMDB 设置, 「多剧混放」→ 去把目录拆开。所以按原因归并
// 计数, 而不是列 N 条同因的路径。两个数组都空时整段不显示 —— 「生成 NFO：0 个」
// 对没勾 NFO 的用户纯属噪音。
const nfoStats = computed(() => {
  const written = props.result?.nfo_written || []
  const skipped = props.result?.nfo_skipped || []
  // 跟随移动的既有 NFO（spec §9.1.1）既不是「写入」也不是「跳过」, 单列一项:
  // 没开 NFO 生成时它就只出现在这里, 漏掉这一项等于这件事彻底不可见。
  const carried = props.result?.nfo_carried || []
  if (!written.length && !skipped.length && !carried.length) return null

  const byReason = new Map()
  for (const item of skipped) {
    const reason = item?.reason || '未说明原因'
    byReason.set(reason, (byReason.get(reason) || 0) + 1)
  }

  return {
    // 干跑时这两个数字是计划而非事实, 由 workspace.executeAction 记在结果上。
    dryRun: props.result?.dry_run === true,
    writtenCount: written.length,
    // 计数之外还要**路径本身**（§9.4）—— 数字说不出 tvshow.nfo 落到哪个目录。
    writtenPaths: written,
    carriedCount: carried.length,
    carriedPaths: carried,
    skippedCount: skipped.length,
    reasonText: [...byReason].map(([reason, count]) => `${reason} ${count} 项`).join('；'),
    hint: byReason.has('已存在')
      ? '如需覆盖既有 NFO，请勾选「覆盖已存在的 NFO」后重新执行'
      : '',
  }
})
</script>

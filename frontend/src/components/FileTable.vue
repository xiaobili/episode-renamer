<template>
  <div class="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface">
    <div class="flex shrink-0 items-center justify-between gap-3 border-b border-line px-4 py-3">
      <div class="flex min-w-0 items-center gap-2 text-[14px] font-semibold text-ink">
        <span class="truncate">文件列表</span>
        <span v-if="filesStore.files.length" class="truncate text-[12px] font-normal text-ink-3">
          共 {{ filesStore.files.length }} 个文件
          <span v-if="scannedInfo"> (视频 {{ scannedInfo.videos }} / 字幕 {{ scannedInfo.subtitles }})</span>
        </span>
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <AppButton
          size="sm"
          variant="secondary"
          :loading="scraping"
          :disabled="!filesStore.files.length || scanning"
          @click="$emit('scrape')"
        >
          刮削标题
        </AppButton>
        <AppButton
          size="sm"
          variant="secondary"
          :disabled="!filesStore.files.length"
          @click="$emit('preview-all')"
        >
          预览
        </AppButton>
        <AppButton
          size="sm"
          variant="danger"
          :disabled="!filesStore.files.length"
          @click="$emit('clear-all')"
        >
          清空
        </AppButton>
      </div>
    </div>

    <!-- 空态：图标 + 标题 + 说明 + 主操作，垂直居中于表格区 -->
    <div
      v-if="!scanning && !previewRows.length"
      class="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-8 text-center"
    >
      <FileQuestion class="h-10 w-10 text-ink-3" aria-hidden="true" />
      <div class="text-[14px] font-medium text-ink">{{ emptyState.title }}</div>
      <p class="max-w-[420px] text-[13px] leading-relaxed text-ink-2">{{ emptyState.description }}</p>
      <AppButton
        v-if="emptyState.action"
        variant="primary"
        class="mt-1"
        @click="$emit(emptyState.action.event)"
      >
        {{ emptyState.action.label }}
      </AppButton>
    </div>

    <!-- 滚动容器。flex-1 + min-h-0 让它吃掉父容器剩余高度并在内部滚动，
         而不是把页面撑高（spec §7.2）。 -->
    <div v-else class="min-h-0 flex-1 overflow-auto" :aria-busy="scanning ? 'true' : undefined">
      <table class="w-full min-w-[560px] text-[13px]" aria-label="文件重命名预览">
        <thead class="sticky top-0 z-[1] bg-sunken">
          <tr class="text-ink-2">
            <th class="hidden w-12 px-4 py-3 text-left font-semibold sm:table-cell">#</th>
            <th class="w-12 px-4 py-3 text-left font-semibold">
              <AppCheckbox
                :model-value="allSelected"
                aria-label="全选"
                @update:model-value="$emit('toggle-all', $event)"
              />
            </th>
            <th class="min-w-[140px] px-4 py-3 text-left font-semibold md:min-w-[220px]">原文件名</th>
            <th class="hidden w-[160px] px-4 py-3 text-left font-semibold md:table-cell">解析剧名</th>
            <!-- 季 / 集：窄屏下这张表是「超约束」的（min-w-[560px] > 视口），浏览器会把
                 各列压到最小内容宽 —— 此刻 w-* 只是提示、会被完全忽略（实测 375px 下把
                 w 从 72 一路调到 128，列宽恒为 54 = 输入框最小内容宽 22 + td 的 32）。
                 54px 的格子里，输入框内宽只剩 0（px-2.5 就吃掉 20px），两位数的集数
                 因此渲染为空白。故这里必须用 min-w-* 立一条**下限**，md 上的 w-[96px]
                 则是宽表里的宽度提示。96px 下输入框内宽 62、可用文字宽 42px，
                 够放 3 位数（13px 字体下 "999" 的前进宽 23.13px、墨迹 21.5px），与
                 :max="999" 相符。 -->
            <th class="min-w-[96px] px-4 py-3 text-left font-semibold md:w-[96px]">季</th>
            <th class="min-w-[96px] px-4 py-3 text-left font-semibold md:w-[96px]">集</th>
            <th class="min-w-[140px] px-4 py-3 text-left font-semibold md:min-w-[180px]">标题</th>
            <th class="w-[80px] px-4 py-3 text-left font-semibold md:w-[96px]">状态</th>
            <th class="hidden px-4 py-3 text-left font-semibold lg:table-cell">TMDB</th>
            <th class="hidden px-4 py-3 text-left font-semibold lg:table-cell">NFO</th>
            <th class="min-w-[140px] px-4 py-3 text-left font-semibold md:min-w-[220px]">新文件名</th>
          </tr>
        </thead>
        <tbody>
          <!-- 加载中：骨架行。条件不是裸的 scanning —— 重新扫描一个已扫过的目录时
               旧数据仍然有效，用预览行是否为空做闸门，首屏才显示骨架。
               脉动动画**不加**：spec §11 的动效表是穷举的五行，没有「骨架呼吸」这一条，
               「正在加载」由形状（8 行按真实列结构排布的灰块）与容器上的忙碌语义标记表达。
               行高与真实数据行一致：59.4px 是在浏览器里量出来的（真实行由 13px 文件名
               + 11px 路径两行 + 上下各 10px 内边距 + 1px 上边框构成），
               取整成 58 或 60 都会与真实行高差一截（1.4px / 0.6px），数据到达时便会有跳动。 -->
          <template v-if="scanning && !previewRows.length">
            <tr
              v-for="n in SKELETON_ROWS"
              :key="`skeleton-${n}`"
              class="h-[59.4px] border-t border-line"
              aria-hidden="true"
            >
              <td class="hidden px-4 py-2.5 sm:table-cell">
                <div class="h-4 w-6 rounded-[4px] bg-sunken" />
              </td>
              <td class="px-4 py-2.5">
                <div class="h-4 w-4 rounded-[4px] bg-sunken" />
              </td>
              <td class="px-4 py-2.5">
                <div class="h-4 w-[240px] rounded-[4px] bg-sunken" />
                <div class="mt-1 h-3 w-[180px] rounded-[4px] bg-sunken" />
              </td>
              <td class="hidden px-4 py-2.5 md:table-cell">
                <div class="h-8 w-[120px] rounded-[4px] bg-sunken" />
              </td>
              <td class="px-4 py-2.5">
                <div class="h-8 w-12 rounded-[4px] bg-sunken" />
              </td>
              <td class="px-4 py-2.5">
                <div class="h-8 w-12 rounded-[4px] bg-sunken" />
              </td>
              <td class="px-4 py-2.5">
                <div class="h-8 w-[120px] rounded-[4px] bg-sunken" />
              </td>
              <td class="px-4 py-2.5">
                <div class="h-6 w-16 rounded-[4px] bg-sunken" />
              </td>
              <td class="hidden px-4 py-2.5 lg:table-cell">
                <div class="h-6 w-16 rounded-[4px] bg-sunken" />
              </td>
              <td class="hidden px-4 py-2.5 lg:table-cell">
                <div class="h-4 w-[140px] rounded-[4px] bg-sunken" />
              </td>
              <td class="px-4 py-2.5">
                <div class="h-4 w-[200px] rounded-[4px] bg-sunken" />
              </td>
            </tr>
          </template>

          <template v-else>
            <tr
              v-for="(row, idx) in previewRows"
              :key="row.id"
              class="border-t border-line transition-colors duration-150 hover:bg-sunken/60"
            >
              <td class="hidden px-4 py-2.5 text-ink-3 tabular-nums sm:table-cell">{{ idx + 1 }}</td>
              <td class="px-4 py-2.5">
                <AppCheckbox
                  :model-value="row.selected"
                  :aria-label="`选择 ${row.filename}`"
                  @update:model-value="$emit('select-row', { row, val: $event })"
                />
              </td>
              <td class="px-4 py-2.5">
                <div class="max-w-[320px] truncate text-ink">{{ row.filename }}</div>
                <div class="max-w-[320px] truncate text-[11px] text-ink-3">{{ row.path }}</div>
              </td>
              <td class="hidden px-4 py-2.5 md:table-cell">
                <AppInput
                  v-model="row.show_name"
                  size="sm"
                  aria-label="解析剧名"
                  @update:model-value="$emit('update-row', row)"
                />
              </td>
              <td class="px-4 py-2.5">
                <AppInput
                  v-model.number="row.season"
                  size="sm"
                  type="number"
                  :min="1"
                  :max="30"
                  aria-label="季"
                  @update:model-value="$emit('update-row', row)"
                />
              </td>
              <td class="px-4 py-2.5">
                <AppInput
                  v-model.number="row.episode"
                  size="sm"
                  type="number"
                  :min="1"
                  :max="999"
                  aria-label="集"
                  @update:model-value="$emit('update-row', row)"
                />
              </td>
              <td class="px-4 py-2.5">
                <AppInput
                  v-model="row.title"
                  size="sm"
                  aria-label="集标题"
                  placeholder="TMDB 标题"
                  @update:model-value="$emit('update-row', row)"
                />
              </td>
              <td class="px-4 py-2.5">
                <AppBadge :tone="row.needs_review ? 'warn' : 'neutral'">
                  <template #icon>
                    <AlertTriangle v-if="row.needs_review" class="h-3.5 w-3.5" aria-hidden="true" />
                    <Check v-else class="h-3.5 w-3.5" aria-hidden="true" />
                  </template>
                  {{ row.needs_review ? '待确认' : '已解析' }}
                </AppBadge>
              </td>
              <td class="hidden px-4 py-2.5 lg:table-cell">
                <div class="flex items-center gap-1.5">
                  <AppBadge :tone="tmdbTone(row.tmdb_status)">
                    {{ tmdbLabel(row.tmdb_status) }}
                  </AppBadge>
                  <button
                    type="button"
                    class="rounded-[6px] p-1 text-ink-3 transition-colors duration-150 hover:bg-sunken hover:text-accent focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
                    :title="row.tmdb_match ? `当前：${row.tmdb_match.name}` : '搜索剧集'"
                    :aria-label="`为 ${row.show_name} 重新选择 TMDB 剧集`"
                    @click="$emit('rematch', row)"
                  >
                    <Search class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </div>
              </td>
              <td class="hidden px-4 py-2.5 lg:table-cell">
                <div v-if="row.nfo" class="flex max-w-[240px] flex-col gap-0.5 text-[11px]">
                  <!-- 本行的 nfo 非空, 只说明「这一行有东西要写」（剧情级 / 季级）,
                       不保证**本集**有。show 匹配上而这一集 TMDB 里没有时
                       （NfoEntry.has_metadata 要求 show 与 episode_data 同时存在）,
                       不会有 episode 键 —— 此前这里渲染成一条空白行, 从不说
                       「本集没有 NFO」。这是行级状态, 与批次级的 nfo_scope
                       （disabled / unsupported_source）不是一回事, 故不复用它的文案。 -->
                  <span v-if="row.nfo.episode" class="break-all text-ink-2" :title="row.nfo.episode">
                    {{ nfoLandingLabel(row.nfo.episode) }}
                  </span>
                  <span v-else class="text-warn" title="TMDB 未匹配到本集，不写本集 NFO">
                    本集无 NFO
                  </span>
                  <span v-if="row.nfo.tvshow" class="break-all text-ink-3" :title="row.nfo.tvshow">
                    + {{ nfoLandingLabel(row.nfo.tvshow) }}
                  </span>
                  <!-- 这条要**两个**条件, 缺任何一个都会打出假警告:
                       ① 不能用「本行 nfo 里没有 tvshow 键」作判据 —— 剧集级决策按契约
                       只挂在组内第一条 file_id 上（build_nfo_decisions 的 group[0]）,
                       所以一个 10 集的剧目录里有 9 行都没有 tvshow 键, 逐行判会给这 9 行
                       打假警告, 而 tvshow.nfo 明明在计划里（nfo_scope 由「按文件」改成
                       「按剧」判定, 修的正是这个根因）;
                       ② 也不能只用批次级的 nfo_scope === 'episode_only' —— 判定按**批**,
                       所以「干净剧 A + 混放 B/C」这样一批里, A 的第二集也会被牵连报
                       「多剧混放」, 而 A 的 tvshow.nfo 就在计划里、还显示在 A 的第一行上。
                       加上 showsWithShowLevelNfo 才落到正确的行: 该集合是「本批里真有
                       剧集级落点的剧名」, full 批次里它含每一部剧 → 全部静默; 同目录混放
                       时它是空集 → 每行都警告; 多目录混放时它只含 A → 只警告 B/C。 -->
                  <span
                    v-else-if="row.nfo_scope === 'episode_only' && !showsWithShowLevelNfo.has(row.show_name)"
                    class="text-warn"
                    :title="nfoScopeHint(row.nfo_scope)"
                  >
                    仅每集 NFO
                  </span>
                  <!-- season.nfo 此前**从不渲染**: 后端把 row.nfo.season 送出来了,
                       前端却没接 —— 于是「季级 NFO 落到哪里」在预览里根本不存在,
                       而 spec §9.4 要求两道剧集级落点都一眼可见。（放在警告链之后
                       是为了不打断 v-if / v-else-if 链: 插在中间会让「仅每集 NFO」
                       变成 season 那一支的 else。） -->
                  <span v-if="row.nfo.season" class="break-all text-ink-3" :title="row.nfo.season">
                    + {{ nfoLandingLabel(row.nfo.season) }}
                  </span>
                </div>
                <span
                  v-else
                  class="text-[11px]"
                  :class="nfoNullHint(row).warn ? 'text-warn' : 'text-ink-3'"
                  :title="nfoNullHint(row).title"
                >{{ nfoNullHint(row).text }}</span>
              </td>
              <td class="px-4 py-2.5">
                <div class="truncate font-medium text-ink" :class="row.new_filename ? '' : 'text-ink-3'">
                  {{ row.new_filename || '(未解析)' }}
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { AlertTriangle, Check, FileQuestion, Search } from 'lucide-vue-next'

import AppBadge from './ui/AppBadge.vue'
import AppButton from './ui/AppButton.vue'
import AppCheckbox from './ui/AppCheckbox.vue'
import AppInput from './ui/AppInput.vue'

// 骨架行数：取一个能填满常见视口的高度，不必等于真实文件数 ——
// 骨架的职责是「占住版面、表达正在加载」，不是「预告有多少行」。
const SKELETON_ROWS = 8

const TMDB_LABELS = {
  matched: '已匹配',
  disabled: '未启用',
  show_not_found: '未匹配',
  season_not_found: '无此季',
  episode_not_found: '无此集',
  unavailable: '不可用',
}

function tmdbLabel(status) {
  // 未刮削时后端报的是 disabled（它确实没被启用），但把这个成因说成「未启用」
  // 会把用户推去设置页翻一个本来就开着的开关。成因必须说对（spec §17.5）。
  if (props.tmdbPendingScrape) return '未刮削'
  return TMDB_LABELS[status] || '未知'
}

function tmdbTone(status) {
  if (props.tmdbPendingScrape) return 'neutral'
  if (status === 'matched') return 'accent'
  if (status === 'disabled') return 'neutral'
  return 'warn'
}

// NFO 落点列的文案表。键必须与后端 `nfo_scope` 的四个取值逐字一致
// （Task 4 产生：disabled / unsupported_source / episode_only / full）——
// 少一个键不会报错，只会让那一行显示成兜底的「—」，看起来像「没有 NFO 计划」，
// 把真实原因藏起来（spec §9.4 要防的正是这种静默）。
const NFO_SCOPE_HINTS = {
  disabled: '未启用',
  unsupported_source: '云盘不支持',
  episode_only: '多剧混放，仅每集 NFO',
  full: '—',
}

// 显示**末两段**（父目录 / 文件名）, 而不是只看 basename。
//
// spec §9.4 要求预览显式列出剧集级 NFO 的绝对路径, 判据是「落点错误时一眼可见」。
// 落点能错在哪? **目录**: 上溯过头时 tvshow.nfo 会落到库根（/m/lib/tvshow.nfo）
// 而不是剧目录（/m/lib/绝命毒师/tvshow.nfo）—— 只显示 basename 时两种情况都是
// 同一行字「tvshow.nfo」, 那句话只在 title 里, 而 title 要悬停才看得见, 且长路径
// 被浏览器截断。末两段把目录带进来, 不悬停也能分辨库根 / 剧目录 / 季目录。
// 全路径仍留在 title 里, 方便复制。
//
// 单段路径（相对路径）没有父目录可显示, 退回整串。
function nfoLandingLabel(path) {
  if (!path) return ''
  const segments = path.split('/').filter(Boolean)
  return segments.slice(-2).join('/')
}

function nfoScopeHint(scope) {
  return NFO_SCOPE_HINTS[scope] || '—'
}

// 只有这两个 scope 是**批次级**事实: 整批都不写 NFO, 所以按行重复报批次原因是对的。
const BATCH_NFO_SCOPES = new Set(['disabled', 'unsupported_source'])

// `nfo` 为 null 的行：本行没有任何落点。三种成因必须分开说 ——
//   · **字幕**：NFO 管线只处理视频（后端 _is_subtitle_file / video_ids 那两处过滤）。
//     字幕行**必然**是 null, 这是正常状态, 不是警告。字幕默认被勾选
//     （workspace 的 includeSubs）, 所以漏掉这一支就是给默认人群的每一行都刷一条
//     橙色假警告, 而它的 title 还会说「TMDB 未匹配到本集」—— 该行自己的 tmdb_status
//     其实是 matched。**文字为真、title 为假、警示色误导**, 三者叠加。
//   · disabled / unsupported_source：整批都不写, 照实报批次原因;
//   · full / episode_only：批次里确实有东西要写, 只是不在本行（本行的 episode 决策
//     content 为 None, 即 TMDB 没匹配到这一集）—— 那是**本行自己的**状态, 说
//     「本集无 NFO」。若这里改报批次原因（如「多剧混放，仅每集 NFO」）, 同一文件状态
//     就会因为「这一行是不是组代表」而渲染成两种不同的字, 读起来像两回事。
// 后两支与非空分支的第一行用同一句话, 正是为了让这两种归属的渲染一致。
// 第四支（未刮削）由 spec §17.5 追加，它也是批次级成因，故紧跟在字幕之后。
function nfoNullHint(row) {
  // is_subtitle 由扫描器给（local_scanner 的 _build_file_info）, 经扫描响应的
  // model_dump 与 workspace 的 `...f` 原样到达行上 —— 不需要在这里再嗅扩展名。
  if (row.is_subtitle) {
    return { text: '字幕不写 NFO', warn: false, title: undefined }
  }
  // 「勾了生成 NFO 但本次没刮削」：后端此时同样报 disabled，而「未启用」会把用户
  // 推去设置页翻一个本来就开着的开关。它是**批次级**成因，故与下面 disabled /
  // unsupported_source 同一位置（在 is_subtitle 之后，与该分支的既有次序一致）。
  // nfoNeedsScrape 已经含了「勾了 NFO」这个条件 —— 没勾时这里仍是「未启用」，对的。
  if (props.nfoNeedsScrape) {
    return { text: '未刮削', warn: false, title: '未刮削标题：NFO 的内容全部来自 TMDB' }
  }
  if (BATCH_NFO_SCOPES.has(row.nfo_scope)) {
    return { text: nfoScopeHint(row.nfo_scope), warn: false, title: undefined }
  }
  return { text: '本集无 NFO', warn: true, title: 'TMDB 未匹配到本集，不写本集 NFO' }
}

const props = defineProps({
  filesStore: { type: Object, required: true },
  previewRows: { type: Array, default: () => [] },
  scannedInfo: Object,
  allSelected: Boolean,
  activeSource: String,
  scanning: { type: Boolean, default: false },
  // 未刮削时 TMDB 列该说「未刮削」（设置页关着时不算 —— 见 scrapeGate 的注释）。
  tmdbPendingScrape: { type: Boolean, default: false },
  // 「勾了生成 NFO 但本次没刮削」：NFO 列要说「未刮削」而不是「未启用」。
  nfoNeedsScrape: { type: Boolean, default: false },
  scraping: { type: Boolean, default: false },
})
defineEmits([
  'preview-all', 'clear-all', 'toggle-all', 'select-row', 'update-row', 'quick-scan', 'rematch',
  'scrape',
])

// 「本批里真的有剧集级落点的剧名」—— 用来把「仅每集 NFO」的警告钉到正确的行上。
//
// 来源是**行上的 nfo**（哪一行拿到了 tvshow 键）, 而不是 nfo_scope: 后者是批次级的,
// 一个干净的剧会因为同批**别的**剧被混放守卫拒绝而一起被标成 episode_only ——
// 那样它每一集都会报「多剧混放」, 而它的 tvshow.nfo 正在计划里。
// 判据必须落在「这一行的剧」上, 这正是 R3-1 那次修的同一个形态（行级信号 vs 批次级事实）。
const showsWithShowLevelNfo = computed(() =>
  new Set(props.previewRows.filter(r => r.nfo?.tvshow).map(r => r.show_name)),
)

// 空态文案随数据源变化：本地源可以直接去扫描，云盘源得先连上才有目录可选。
const emptyState = computed(() => {
  if (props.activeSource === 'openlist') {
    return {
      title: '尚未加载文件',
      description: '在左侧「扫描源」里连接 OpenList、选择挂载点与目录，然后点扫描。',
      action: null,
    }
  }
  return {
    title: '尚未加载文件',
    description: '在左侧「扫描源」里选择目录并点击扫描，文件会在这里列出并自动生成新文件名预览。',
    action: { label: '开始扫描', event: 'quick-scan' },
  }
})
</script>

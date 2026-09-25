<template>
  <aside
    class="flex max-h-[45dvh] min-h-0 shrink-0 flex-col overflow-y-auto border-b border-line bg-canvas lg:h-full lg:max-h-none lg:w-[280px] lg:shrink-0 lg:border-b-0 lg:border-r"
  >
    <!-- 窄屏（<1024px）整体折叠头：spec §7.3 要求此档默认收起。
         大屏下 lg:hidden 隐藏它，内容由下面的 lg:block 强制展开。 -->
    <button
      type="button"
      class="flex shrink-0 items-center justify-between gap-2 px-4 py-3 text-[13px] font-medium text-ink-2 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas focus-visible:outline-none lg:hidden"
      :aria-expanded="railOpen"
      @click="railOpen = !railOpen"
    >
      扫描源与模板
      <ChevronDown
        class="h-4 w-4 shrink-0 transition-transform duration-150"
        :class="railOpen ? 'rotate-180' : ''"
        aria-hidden="true"
      />
    </button>

    <div :class="railOpen ? 'block' : 'hidden'" class="lg:block">
      <section class="border-b border-line">
        <button
          type="button"
          class="flex w-full items-center gap-1.5 px-4 py-2.5 text-[12px] font-semibold text-ink-2 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas focus-visible:outline-none"
          :aria-expanded="groups.source"
          @click="groups.source = !groups.source"
        >
          <ChevronRight
            class="h-3.5 w-3.5 shrink-0 transition-transform duration-150"
            :class="groups.source ? 'rotate-90' : ''"
            aria-hidden="true"
          />
          扫描源
        </button>
        <div v-show="groups.source" class="px-4 pb-4">
          <slot name="source" />
        </div>
      </section>

      <section>
        <button
          type="button"
          class="flex w-full items-center gap-1.5 px-4 py-2.5 text-[12px] font-semibold text-ink-2 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas focus-visible:outline-none"
          :aria-expanded="groups.template"
          @click="groups.template = !groups.template"
        >
          <ChevronRight
            class="h-3.5 w-3.5 shrink-0 transition-transform duration-150"
            :class="groups.template ? 'rotate-90' : ''"
            aria-hidden="true"
          />
          重命名模板
        </button>
        <div v-show="groups.template" class="px-4 pb-4">
          <slot name="template" />
        </div>
      </section>
    </div>
  </aside>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ChevronDown, ChevronRight } from 'lucide-vue-next'

// 两级折叠：
//   1. railOpen —— 只在 <1024px 生效（spec §7.3：此档左栏折叠为顶栏下的可展开面板，
//      默认收起）。默认 false；大屏靠 lg:block 强制展开，不受此值影响。
//   2. groups.* —— 分组级折叠，与 spec §7.1 示意图里的 ▸ 对应，两档都生效。
//
// 折叠规则显式声明在本组件内部，不依赖 Tailwind 的自动兜底（spec §7.3 末句）。
const railOpen = ref(false)
const groups = reactive({ source: true, template: true })
</script>

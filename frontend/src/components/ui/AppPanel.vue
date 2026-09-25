<template>
  <section class="rounded-[12px] border border-line bg-surface">
    <header v-if="title" class="border-b border-line px-4 py-3">
      <h2 class="text-[14px] font-semibold text-ink">{{ title }}</h2>
    </header>
    <div class="p-4">
      <slot />
    </div>
  </section>
</template>

<script setup>
// 发丝线容器，替代旧的「白卡片 + shadow-sm」。层级靠 12px 圆角 + 1px 发丝线
// + 与 canvas 背景的明度差表达，不用阴影（spec §5.4）。
//
// 刻意只做「标题 + 内容」两件事：spec §8.1 对它的定义就是「发丝线容器」。
// 不做 actions 插槽 —— 唯一需要「标题 + 右侧操作」的地方是 FileTable 的
// 表格头，而它是撑满工作区的主区域、不是卡片，用不上 AppPanel。
// 等真有调用点再加。
defineProps({
  title: { type: String, default: '' },
})
</script>

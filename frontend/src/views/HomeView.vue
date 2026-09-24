<template>
  <div class="flex flex-col gap-4">
    <div class="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
      <div class="flex border-b border-border bg-surface-muted">
        <button
          v-for="src in sources"
          :key="src.name"
          class="px-5 py-3 text-[13px] font-medium transition-all relative"
          :class="activeSource === src.name
            ? 'text-primary font-semibold bg-surface'
            : 'text-text-secondary hover:text-text'"
          @click="switchSource(src.name)"
        >
          <span class="mr-1.5">{{ src.icon }}</span>{{ src.label }}
          <span
            v-if="activeSource === src.name"
            class="absolute bottom-0 left-0 right-0 h-0.5 bg-primary"
          />
        </button>
      </div>
    </div>

    <Transition name="source-fade" mode="out-in">
    <div :key="activeSource" class="flex flex-col gap-4">

    <div class="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
      <div class="p-6">
        <template v-if="activeSource === 'local'">
          <div class="flex items-center gap-3 flex-wrap">
            <div class="flex-1 min-w-[280px] relative">
              <Folder class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-faint" />
              <input
                v-model="localPath"
                type="text"
                placeholder="输入要扫描的目录路径，如 /home/user/Movies"
                class="w-full h-10 pl-9 pr-3 rounded-lg border border-border bg-surface text-[13px] outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                @keyup.enter="doScan"
              />
            </div>
            <label class="flex items-center gap-2 text-[13px] text-text-secondary cursor-pointer select-none">
              <input type="checkbox" v-model="recursive" class="w-4 h-4 accent-primary rounded" />
              递归扫描
            </label>
            <label class="flex items-center gap-2 text-[13px] text-text-secondary cursor-pointer select-none">
              <input type="checkbox" v-model="includeSubs" class="w-4 h-4 accent-primary rounded" />
              包含字幕
            </label>
            <button
              class="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium flex items-center gap-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="scanning"
              @click="doScan"
            >
              <Search class="w-4 h-4" />
              {{ scanning ? '扫描中...' : '扫描' }}
            </button>
          </div>
        </template>

        <template v-else>
          <template v-if="!olStore.connected">
            <div class="flex items-center gap-3 flex-wrap">
              <div class="flex items-center gap-2">
                <span class="text-[13px] text-text-secondary">服务器</span>
                <input
                  v-model="olForm.server_url"
                  type="text"
                  placeholder="http://localhost:5244"
                  class="w-[220px] h-10 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                />
              </div>
              <div class="flex items-center gap-2">
                <span class="text-[13px] text-text-secondary">用户名</span>
                <input
                  v-model="olForm.username"
                  type="text"
                  placeholder="admin"
                  class="w-[140px] h-10 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                />
              </div>
              <div class="flex items-center gap-2">
                <span class="text-[13px] text-text-secondary">密码</span>
                <input
                  v-model="olForm.password"
                  type="password"
                  placeholder="••••••"
                  show-password
                  class="w-[160px] h-10 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                />
              </div>
              <button
                class="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium flex items-center gap-2 transition disabled:opacity-50"
                :disabled="olStore.loading"
                @click="doOpenListLogin"
              >
                <Zap class="w-4 h-4" />
                {{ olStore.loading ? '连接中...' : '连接' }}
              </button>
            </div>
          </template>

          <template v-else>
            <div class="flex items-center gap-3 flex-wrap">
              <div class="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-success-light text-success text-[12px] font-medium">
                <CheckCircle2 class="w-3.5 h-3.5" />
                已连接: {{ olStore.serverUrl }}
              </div>

              <select
                v-model="olStore.selectedMount"
                @change="onMountChange"
                class="h-10 px-3 rounded-lg border border-border bg-surface text-[13px] text-text outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              >
                <option v-for="m in olStore.mountPoints" :key="m" :value="m">{{ m }}</option>
              </select>

              <div
                class="flex-1 min-w-[280px] h-10 px-3 rounded-lg border border-border bg-surface cursor-pointer hover:border-primary transition flex items-center gap-2"
                @click="openBrowseDialog"
              >
                <Folder class="w-4 h-4 text-text-faint shrink-0" />
                <span
                  v-if="openlistBrowsePath"
                  class="text-[13px] text-text truncate flex-1"
                >{{ openlistBrowsePath }}</span>
                <span v-else class="text-[13px] text-text-faint flex-1">点击浏览选择目录</span>
                <FolderSearch class="w-4 h-4 text-text-muted" />
              </div>

              <button
                class="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium flex items-center gap-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="scanning"
                @click="doOpenListScan"
              >
                <Search class="w-4 h-4" />
                {{ scanning ? '扫描中...' : '扫描' }}
              </button>
              <button
                class="h-10 px-4 bg-surface hover:bg-surface-muted border border-border-strong text-text-secondary hover:text-primary rounded-lg text-[13px] font-medium flex items-center gap-2 transition"
                @click="doOpenListLogout"
              >
                <LogOut class="w-4 h-4" />
                断开
              </button>
            </div>
          </template>
        </template>
      </div>
    </div>

    <div class="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
      <div class="px-6 py-4 border-b border-border flex items-center justify-between">
        <div class="flex items-center gap-2 font-semibold text-[14px] text-text">
          <FileText class="w-4 h-4 text-primary" />
          重命名模板
        </div>
      </div>
      <div class="p-6">
        <div class="flex items-center gap-3 flex-wrap">
          <select
            v-model="tplStore.currentPresetId"
            @change="onPresetChange"
            class="h-10 px-3 rounded-lg border border-border bg-surface text-[13px] text-text outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 w-[220px]"
          >
            <option value="">选择预设模板</option>
            <option v-for="p in tplStore.presets" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
          <input
            v-model="tplStore.currentTemplate"
            placeholder="自定义模板"
            @input="onTemplateEdit"
            class="flex-1 min-w-[260px] h-10 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 font-mono"
          />
          <label
            class="flex items-center gap-2 text-[13px] select-none transition"
            :class="activeSource === 'openlist'
              ? 'text-text-faint cursor-not-allowed'
              : 'text-text-secondary cursor-pointer'"
            :title="activeSource === 'openlist' ? 'OpenList 暂不支持自动创建季文件夹' : ''"
          >
            <input
              type="checkbox"
              v-model="tplStore.createSeasonFolder"
              class="w-4 h-4 accent-primary rounded disabled:opacity-40 disabled:cursor-not-allowed"
              :disabled="activeSource === 'openlist'"
            />
            创建季文件夹
          </label>
          <input
            v-if="tplStore.createSeasonFolder"
            v-model="tplStore.folderTemplate"
            placeholder="季文件夹模板，如 Season {season_padded}"
            class="w-[240px] h-10 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 font-mono"
          />
        </div>
        <div class="mt-4 text-[12px] text-text-muted flex items-center flex-wrap gap-1.5">
          <span>可用变量:</span>
          <span
            v-for="v in templateVars"
            :key="v"
            class="inline-block px-2 py-0.5 rounded bg-surface-muted text-text-secondary font-mono text-[11px]"
          >{{ v }}</span>
        </div>
      </div>
    </div>

    <div class="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
      <div class="px-6 py-4 border-b border-border flex items-center justify-between">
        <div class="flex items-center gap-2 font-semibold text-[14px] text-text">
          <List class="w-4 h-4 text-primary" />
          文件列表
          <span v-if="filesStore.files.length" class="text-[12px] font-normal text-text-muted ml-2">
            共 {{ filesStore.files.length }} 个文件
            <span v-if="scannedInfo"> (视频 {{ scannedInfo.videos }} / 字幕 {{ scannedInfo.subtitles }})</span>
          </span>
        </div>
        <div class="flex items-center gap-2">
          <button
            class="h-8 px-3 bg-surface hover:bg-surface-muted border border-border-strong text-text-secondary hover:text-primary rounded-md text-[12px] font-medium flex items-center gap-1.5 transition disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="!filesStore.files.length"
            @click="previewAll"
          >
            <Eye class="w-3.5 h-3.5" />
            预览
          </button>
          <button
            class="h-8 px-3 bg-error-light hover:bg-error hover:text-white border border-error text-error rounded-md text-[12px] font-medium flex items-center gap-1.5 transition disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="!filesStore.files.length"
            @click="clearAll"
          >
            <Trash2 class="w-3.5 h-3.5" />
            清空
          </button>
        </div>
      </div>

      <div class="relative">
        <div
          v-if="filesStore.scanning"
          class="absolute inset-0 bg-white/60 z-10 flex items-center justify-center"
        >
          <div class="text-text-muted text-[13px]">扫描中...</div>
        </div>
        <div class="overflow-auto" style="max-height: 480px">
          <table class="w-full text-[13px]">
            <thead class="bg-surface-muted sticky top-0 z-[1]">
              <tr class="text-text-secondary">
                <th class="w-12 px-4 py-3 text-left font-semibold">#</th>
                <th class="w-12 px-4 py-3 text-left font-semibold">
                  <input
                    type="checkbox"
                    :checked="allSelected"
                    class="w-4 h-4 accent-primary rounded"
                    @change="toggleAll"
                  />
                </th>
                <th class="px-4 py-3 text-left font-semibold min-w-[220px]">原文件名</th>
                <th class="px-4 py-3 text-left font-semibold w-[160px]">解析剧名</th>
                <th class="px-4 py-3 text-left font-semibold w-[90px]">季</th>
                <th class="px-4 py-3 text-left font-semibold w-[90px]">集</th>
                <th class="px-4 py-3 text-left font-semibold w-[80px]">置信度</th>
                <th class="px-4 py-3 text-left font-semibold min-w-[220px]">新文件名</th>
              </tr>
            </thead>
            <tbody>
              <template v-if="previewRows.length">
                <tr
                  v-for="(row, idx) in previewRows"
                  :key="row.id"
                  class="border-t border-border hover:bg-primary-light/40 transition"
                >
                  <td class="px-4 py-2.5 text-text-faint">{{ idx + 1 }}</td>
                  <td class="px-4 py-2.5">
                    <input type="checkbox" v-model="row.selected" class="w-4 h-4 accent-primary rounded" />
                  </td>
                  <td class="px-4 py-2.5">
                    <div class="text-text truncate max-w-[320px]">{{ row.filename }}</div>
                    <div class="text-[11px] text-text-faint truncate max-w-[320px]">{{ row.path }}</div>
                  </td>
                  <td class="px-4 py-2.5">
                    <input
                      v-model="row.show_name"
                      @change="updatePreview(row)"
                      class="w-full h-8 px-2.5 rounded-md border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                    />
                  </td>
                  <td class="px-4 py-2.5">
                    <input
                      v-model.number="row.season"
                      @change="updatePreview(row)"
                      type="number" min="1" max="30"
                      class="w-full h-8 px-2.5 rounded-md border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                    />
                  </td>
                  <td class="px-4 py-2.5">
                    <input
                      v-model.number="row.episode"
                      @change="updatePreview(row)"
                      type="number" min="1" max="999"
                      class="w-full h-8 px-2.5 rounded-md border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                    />
                  </td>
                  <td class="px-4 py-2.5">
                    <span
                      class="inline-block px-2 py-0.5 rounded text-[11px] font-medium"
                      :class="row.needs_review
                        ? 'bg-warning-light text-warning'
                        : 'bg-success-light text-success'"
                    >{{ row.needs_review ? '⚠️ 待确认' : '✅ 已解析' }}</span>
                  </td>
                  <td class="px-4 py-2.5">
                    <div
                      class="truncate font-medium"
                      :class="row.new_filename && row.new_filename !== row.filename ? 'text-success' : 'text-text-muted'"
                    >
                      {{ row.new_filename || '(未解析)' }}
                    </div>
                  </td>
                </tr>
              </template>
              <tr v-else>
                <td colspan="8" class="px-4 py-16 text-center">
                  <div class="flex flex-col items-center gap-2 text-text-muted">
                    <FileQuestion class="w-10 h-10 text-text-faint" />
                    <div class="text-[13px]">扫描目录以加载文件</div>
                    <button
                      v-if="activeSource === 'local'"
                      class="mt-2 h-9 px-4 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium transition"
                      @click="doScan"
                    >开始扫描</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    </div>
    </Transition>

    <div class="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
      <div class="px-6 py-4 flex items-center justify-between flex-wrap gap-3">
        <div class="flex items-center gap-2 text-[13px] text-text-secondary">
          <span>冲突策略:</span>
          <select
            v-model="conflictStrategy"
            class="h-8 px-2.5 rounded-md border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
          >
            <option label="跳过" value="skip" />
            <option label="中止" value="abort" />
            <option label="覆盖" value="overwrite" />
            <option label="自动编号" value="rename_dup" />
          </select>
        </div>
        <div class="flex items-center gap-3">
          <button
            class="h-10 px-5 bg-surface hover:bg-surface-muted border border-border-strong text-text-secondary hover:text-primary rounded-lg text-[13px] font-medium flex items-center gap-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="!selectedCount"
            @click="doDryRun"
          >
            <Play class="w-4 h-4" />
            试运行 (Dry Run)
          </button>
          <button
            class="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium flex items-center gap-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="!selectedCount"
            @click="doExecute"
          >
            <Rocket class="w-4 h-4" />
            {{ executing ? '执行中...' : '执行重命名' }}
          </button>
        </div>
      </div>
    </div>

    <Transition name="modal">
    <div
      v-if="confirmDialog"
      class="fixed inset-0 z-[55] flex items-center justify-center bg-black/40 p-4"
      @click.self="onConfirmCancel"
    >
      <div class="bg-surface rounded-xl shadow-2xl w-full max-w-[420px] overflow-hidden">
        <div class="px-6 py-5 flex items-start gap-4">
          <div class="w-10 h-10 rounded-full bg-warning-light flex items-center justify-center shrink-0">
            <AlertTriangle class="w-5 h-5 text-warning" />
          </div>
          <div class="flex-1">
            <div class="font-semibold text-[15px] text-text mb-1">确认执行</div>
            <div class="text-[13px] text-text-secondary leading-relaxed">{{ confirmMessage }}</div>
          </div>
        </div>
        <div class="px-6 py-3 border-t border-border bg-surface-muted flex justify-end gap-2">
          <button
            class="h-9 px-4 bg-surface hover:bg-border border border-border-strong rounded-lg text-[13px] font-medium text-text-secondary hover:text-text transition"
            @click="onConfirmCancel"
          >取消</button>
          <button
            class="h-9 px-5 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium transition"
            @click="onConfirmOk"
          >确定</button>
        </div>
      </div>
    </div>
    </Transition>

    <Transition name="modal">
    <div
      v-if="executing"
      class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 backdrop-blur-sm"
    >
      <div class="bg-surface rounded-2xl shadow-2xl w-[340px] p-7 flex flex-col items-center gap-4">
        <div class="relative w-14 h-14">
          <div class="absolute inset-0 rounded-full border-4 border-primary/20" />
          <div class="absolute inset-0 rounded-full border-4 border-transparent border-t-primary animate-[spin_0.9s_linear_infinite]" />
          <Rocket class="absolute inset-0 m-auto w-6 h-6 text-primary animate-[bounce_1.4s_ease-in-out_infinite]" />
        </div>
        <div class="text-center">
          <div class="text-[15px] font-semibold text-text mb-1">
            {{ executeDryRun ? '试运行中...' : '正在执行重命名...' }}
          </div>
          <div class="text-[12px] text-text-muted">请稍候，操作进行中请勿关闭</div>
        </div>
      </div>
    </div>
    </Transition>

    <Transition name="modal">
    <div
      v-if="resultDialog"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      @click.self="resultDialog = false"
    >
      <div class="bg-surface rounded-xl shadow-2xl w-full max-w-[700px] max-h-[85vh] overflow-hidden">
        <div class="px-6 py-4 border-b border-border flex items-center justify-between">
          <div class="font-semibold text-[15px] text-text">重命名结果</div>
          <button class="text-text-faint hover:text-text transition" @click="resultDialog = false">
            <X class="w-5 h-5" />
          </button>
        </div>
        <div class="p-6 overflow-auto max-h-[calc(85vh-130px)]">
          <template v-if="lastResult">
            <div class="grid grid-cols-4 gap-4 mb-4">
              <div class="text-center p-3 rounded-lg bg-surface-muted">
                <div class="text-[11px] text-text-muted">数据源</div>
                <div class="text-sm font-semibold mt-1">{{ lastResult.source }}</div>
              </div>
              <div class="text-center p-3 rounded-lg bg-success-light">
                <div class="text-[11px] text-success">成功</div>
                <div class="text-sm font-bold mt-1 text-success">{{ lastResult.executed }}</div>
              </div>
              <div class="text-center p-3 rounded-lg bg-surface-muted">
                <div class="text-[11px] text-text-muted">跳过</div>
                <div class="text-sm font-bold mt-1 text-text-secondary">{{ lastResult.skipped }}</div>
              </div>
              <div class="text-center p-3 rounded-lg" :class="lastResult.failed ? 'bg-error-light' : 'bg-surface-muted'">
                <div class="text-[11px]" :class="lastResult.failed ? 'text-error' : 'text-text-muted'">失败</div>
                <div class="text-sm font-bold mt-1" :class="lastResult.failed ? 'text-error' : 'text-text-secondary'">{{ lastResult.failed }}</div>
              </div>
            </div>
            <table v-if="lastResult.results?.length" class="w-full text-[12px]">
              <thead class="bg-surface-muted">
                <tr class="text-text-secondary">
                  <th class="px-3 py-2 text-left font-semibold">原文件名</th>
                  <th class="px-3 py-2 text-left font-semibold">新文件名</th>
                  <th class="px-3 py-2 text-left font-semibold w-[80px]">状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(r, i) in lastResult.results" :key="i" class="border-t border-border">
                  <td class="px-3 py-2 text-text truncate max-w-[200px]">{{ r.original_filename }}</td>
                  <td class="px-3 py-2 text-text truncate max-w-[200px]">{{ r.new_filename }}</td>
                  <td class="px-3 py-2">
                    <span
                      class="inline-block px-2 py-0.5 rounded text-[11px] font-medium"
                      :class="r.success ? 'bg-success-light text-success' : 'bg-error-light text-error'"
                    >{{ r.status }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </template>
        </div>
        <div class="px-6 py-3 border-t border-border flex justify-end">
          <button
            class="h-9 px-4 bg-surface-muted hover:bg-border rounded-lg text-[13px] font-medium transition"
            @click="resultDialog = false"
          >关闭</button>
        </div>
      </div>
    </div>
    </Transition>

    <Transition name="modal">
    <div
      v-if="browseDialog"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      @click.self="browseDialog = false"
    >
      <div class="bg-surface rounded-xl shadow-2xl w-full max-w-[520px] overflow-hidden">
        <div class="px-6 py-4 border-b border-border flex items-center justify-between">
          <div class="font-semibold text-[15px] text-text">选择目录</div>
          <button class="text-text-faint hover:text-text transition" @click="browseDialog = false">
            <X class="w-5 h-5" />
          </button>
        </div>
        <div class="p-6">
          <div class="flex items-center gap-2 mb-4 pb-3 border-b border-border">
            <button
              class="h-8 px-3 rounded-md bg-surface-muted hover:bg-border text-[12px] text-text-secondary hover:text-text transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
              :disabled="!browseCurrent || browseCurrent === browseRoot"
              @click="browseTo(browseParent)"
            >
              <ChevronLeft class="w-4 h-4" />上级
            </button>
            <div class="flex-1 flex items-center gap-1 text-[12px] text-text-muted overflow-hidden">
              <template v-for="(seg, idx) in browseBreadcrumbs" :key="idx">
                <span
                  class="cursor-pointer hover:text-primary transition truncate"
                  @click="browseTo(seg.path)"
                >{{ seg.name }}</span>
                <ChevronRight v-if="idx < browseBreadcrumbs.length - 1" class="w-3 h-3 shrink-0 text-text-faint" />
              </template>
            </div>
          </div>

          <div v-if="browseLoading" class="py-12 text-center text-text-muted text-[13px]">加载中...</div>
          <div v-else-if="!browseDirs.length" class="py-12 text-center text-text-muted text-[13px]">此目录无子目录</div>
          <div v-else class="max-h-[320px] overflow-auto">
            <div
              v-for="d in browseDirs"
              :key="d.path"
              class="flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg cursor-pointer transition-all"
              :class="browseSelected?.path === d.path
                ? 'bg-primary-light text-primary'
                : 'hover:bg-surface-muted text-text'"
              @click="browsePick(d)"
              @dblclick="browseTo(d.path)"
            >
              <Folder class="w-[18px] h-[18px] shrink-0" :class="browseSelected?.path === d.path ? 'text-primary' : 'text-text-faint'" />
              <span class="text-[14px] font-medium truncate">{{ d.name }}</span>
            </div>
          </div>
        </div>
        <div class="px-6 py-3 border-t border-border flex justify-end gap-2">
          <button
            class="h-9 px-4 bg-surface-muted hover:bg-border rounded-lg text-[13px] font-medium transition"
            @click="browseDialog = false"
          >取消</button>
          <button
            class="h-9 px-4 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="!browseSelected"
            @click="browseConfirm"
          >确定选择</button>
        </div>
      </div>
    </div>
    </Transition>

    <div
      v-if="toast.show"
      class="fixed top-6 right-6 z-[100] flex items-center gap-2 px-4 py-2.5 rounded-lg shadow-lg text-[13px] font-medium animate-[slideIn_0.2s_ease]"
      :class="{
        'bg-success-light text-success': toast.type === 'success',
        'bg-error-light text-error': toast.type === 'error',
        'bg-warning-light text-warning': toast.type === 'warning',
        'bg-primary-light text-primary': toast.type === 'info',
      }"
    >
      <CheckCircle2 v-if="toast.type === 'success'" class="w-4 h-4" />
      <XCircle v-else-if="toast.type === 'error'" class="w-4 h-4" />
      <AlertTriangle v-else-if="toast.type === 'warning'" class="w-4 h-4" />
      <Info v-else class="w-4 h-4" />
      {{ toast.msg }}
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import {
  Folder, FolderSearch, Search, Eye, Trash2, CheckCircle2, XCircle, AlertTriangle, Info,
  FileText, List, Play, Rocket, X, ChevronLeft, ChevronRight, LogOut, Zap, FileQuestion,
} from 'lucide-vue-next'

import { useFilesStore } from '../stores/files'
import { useTemplateStore } from '../stores/template'
import { useOpenListStore } from '../stores/openlist'

import { scanDirectory } from '../api/scanner'
import { previewRename, executeRename, dryRunRename } from '../api/renamer'
import { getPresets } from '../api/template'
import { openlistLogin, openlistLogout as apiLogout, openlistStatus as apiOlStatus, openlistBrowse } from '../api/openlist'

const sources = [
  { name: 'local', label: '本地磁盘', icon: '📁' },
  { name: 'openlist', label: 'OpenList 云盘', icon: '☁️' },
]

const toast = reactive({ show: false, type: 'info', msg: '' })
let toastTimer = null
function showToast(msg, type = 'info') {
  toast.msg = msg
  toast.type = type
  toast.show = true
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.show = false }, 2800)
}

const filesStore = useFilesStore()
const tplStore = useTemplateStore()
const olStore = useOpenListStore()

const activeSource = ref('local')
const localPath = ref('')
const openlistBrowsePath = ref('')
const recursive = ref(true)
const includeSubs = ref(true)
const scanning = ref(false)
const executing = ref(false)
const executeDryRun = ref(false)
const confirmDialog = ref(false)
const confirmMessage = ref('')
let confirmResolver = null
const conflictStrategy = ref('skip')
const scannedInfo = ref(null)
const resultDialog = ref(false)
const lastResult = ref(null)

const browseDialog = ref(false)
const browseLoading = ref(false)
const browseCurrent = ref('')
const browseParent = ref('')
const browseRoot = ref('')
const browseDirs = ref([])
const browseSelected = ref(null)

const olForm = reactive({ server_url: '', username: '', password: '' })

const templateVars = ['{show}', '{season}', '{season_padded}', '{episode}', '{episode_padded}', '{extension}', '{quality}', '{source}', '{sub_lang}']

const previewRows = ref([])

const allSelected = computed(() => {
  const selected = previewRows.value.filter(r => r.selected)
  return selected.length > 0 && selected.length === previewRows.value.length
})

const selectedCount = computed(() => {
  return previewRows.value.filter(r => r.selected).length
})

const browseBreadcrumbs = computed(() => {
  const root = browseRoot.value
  const cur = browseCurrent.value
  const segs = [{ name: root || '/', path: root || '/' }]
  if (cur && cur !== root) {
    const rel = cur.startsWith(root) ? cur.slice(root.length) : cur
    rel.split('/').filter(Boolean).forEach((part, i, arr) => {
      segs.push({
        name: part,
        path: root + '/' + arr.slice(0, i + 1).join('/'),
      })
    })
  }
  return segs
})

onMounted(async () => {
  const res = await getPresets()
  if (res.data?.data) {
    tplStore.presets = res.data.data
    const def = tplStore.presets.find(p => p.id === tplStore.currentPresetId)
    if (def) tplStore.setPreset(def)
  }

  olForm.server_url = olStore.serverUrl || ''
  olForm.username = olStore.username || ''

  const statusRes = await apiOlStatus()
  if (statusRes.data?.connected) {
    olStore.setConnection(true, statusRes.data)
  }
})

function switchSource(name) {
  if (name === activeSource.value) return
  activeSource.value = name
  filesStore.clear()
  previewRows.value = []
  scannedInfo.value = null
  if (name === 'openlist') {
    tplStore.createSeasonFolder = false
  }
}

async function doScan() {
  if (!localPath.value) {
    showToast('请输入目录路径', 'warning')
    return
  }
  scanning.value = true
  try {
    const res = await scanDirectory({
      source: 'local',
      path: localPath.value,
      recursive: recursive.value,
      include_subtitles: includeSubs.value,
    })
    const data = res.data
    filesStore.source = 'local'
    filesStore.setFiles(data.files || [])
    filesStore.scanResult = data
    scannedInfo.value = data
    showToast(`扫描完成，发现 ${data.total_files} 个文件`, 'success')
    await buildPreview()
  } catch (e) {
    showToast('扫描失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    scanning.value = false
  }
}

async function doOpenListLogin() {
  olStore.loading = true
  try {
    const res = await openlistLogin({
      server_url: olForm.server_url,
      username: olForm.username,
      password: olForm.password,
    })
    const data = res.data
    olStore.setConnection(true, data)
    showToast('连接成功', 'success')
  } catch (e) {
    showToast('连接失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    olStore.loading = false
  }
}

async function doOpenListLogout() {
  await apiLogout()
  olStore.disconnect()
  showToast('已断开', 'info')
}

async function doOpenListScan() {
  if (!openlistBrowsePath.value || openlistBrowsePath.value === olStore.selectedMount) {
    showToast('请浏览选择具体的子目录后再扫描', 'warning')
    browseDialog.value = true
    browseLoad(olStore.selectedMount)
    return
  }
  scanning.value = true
  try {
    const res = await scanDirectory({
      source: 'openlist',
      path: openlistBrowsePath.value,
      recursive: recursive.value,
      include_subtitles: includeSubs.value,
    })
    const data = res.data
    filesStore.source = 'openlist'
    filesStore.setFiles(data.files || [])
    filesStore.scanResult = data
    scannedInfo.value = data
    showToast(`扫描完成，发现 ${data.total_files} 个文件`, 'success')
    await buildPreview()
  } catch (e) {
    showToast('扫描失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    scanning.value = false
  }
}

function onMountChange() {
  openlistBrowsePath.value = ''
}

function openBrowseDialog() {
  const mount = olStore.selectedMount || ''
  browseRoot.value = mount
  browseParent.value = mount
  browseCurrent.value = mount
  browseSelected.value = null
  browseDirs.value = []
  browseDialog.value = true
  browseLoad(mount)
}

async function browseLoad(path) {
  browseLoading.value = true
  try {
    const res = await openlistBrowse(path)
    const data = res.data
    browseDirs.value = data.dirs || []
    browseParent.value = data.parent
    browseCurrent.value = data.path
  } catch (e) {
    showToast('加载目录失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    browseLoading.value = false
  }
}

function browsePick(d) {
  browseSelected.value = d
}

function browseTo(path) {
  if (!path || path === browseCurrent.value) return
  browseLoad(path)
}

function browseConfirm() {
  const pick = browseSelected.value
  if (!pick) return
  if (pick.path === olStore.selectedMount) {
    showToast('不能选择云盘根目录，请进入子文件夹后再选择', 'warning')
    return
  }
  openlistBrowsePath.value = pick.path
  browseDialog.value = false
}

function onPresetChange() {
  const preset = tplStore.presets.find(p => p.id === tplStore.currentPresetId)
  if (preset) tplStore.setPreset(preset)
  buildPreview()
}

function onTemplateEdit() {
  tplStore.currentPresetId = ''
  buildPreview()
}

async function buildPreview() {
  if (!filesStore.files.length) {
    previewRows.value = []
    return
  }
  try {
    const ids = filesStore.files.map(f => f.id)
    const res = await previewRename({
      file_ids: ids,
      source: filesStore.source,
      path: filesStore.files[0].path.replace(filesStore.files[0].filename, ''),
      template: tplStore.currentTemplate,
      folder_template: tplStore.folderTemplate,
      create_season_folder: tplStore.createSeasonFolder,
    })
    const previews = res.data.results || []
    previewRows.value = filesStore.files.map(f => {
      const pv = previews.find(p => p.original_path === f.path) || {}
      return {
        ...f,
        selected: true,
        show_name: pv.show_name || '',
        season: pv.season,
        episode: pv.episode,
        new_filename: pv.new_filename || '',
        needs_review: pv.needs_review || false,
        confidence: pv.confidence || 0,
        override: {},
      }
    })
  } catch (e) {
    console.error(e)
  }
}

function updatePreview(row) {
  row.override = {
    show_name: row.show_name,
    season: row.season,
    episode: row.episode,
  }
}

function toggleAll(val) {
  previewRows.value.forEach(r => { r.selected = val })
}

async function previewAll() {
  await buildPreview()
  showToast('预览已刷新', 'success')
}

function clearAll() {
  showConfirm('确定清空文件列表？这将移除当前扫描到的所有文件。').then(ok => {
    if (ok) {
      filesStore.clear()
      previewRows.value = []
      scannedInfo.value = null
    }
  })
}

async function showConfirm(message) {
  confirmMessage.value = message
  confirmDialog.value = true
  return new Promise(resolve => {
    confirmResolver = resolve
  })
}

function onConfirmOk() {
  confirmDialog.value = false
  if (confirmResolver) {
    confirmResolver(true)
    confirmResolver = null
  }
}

function onConfirmCancel() {
  confirmDialog.value = false
  if (confirmResolver) {
    confirmResolver(false)
    confirmResolver = null
  }
}

async function doDryRun() {
  await executeAction(true)
}

async function doExecute() {
  const ok = await showConfirm(`将对 ${selectedCount.value} 个文件执行重命名操作，确认继续？`)
  if (!ok) return
  await executeAction(false)
}

async function executeAction(dryRun = false) {
  const selected = previewRows.value.filter(r => r.selected)
  if (!selected.length) {
    showToast('请先选择文件', 'warning')
    return
  }

  executing.value = !dryRun
  executeDryRun.value = dryRun
  try {
    const overrides = {}
    selected.forEach(r => {
      if (r.override) overrides[r.id] = r.override
    })
    const ids = selected.map(r => r.id)
    const fn = dryRun ? dryRunRename : executeRename
    const res = await fn({
      file_ids: ids,
      source: filesStore.source,
      path: selected[0].path.replace(selected[0].filename, ''),
      template: tplStore.currentTemplate,
      folder_template: tplStore.folderTemplate,
      create_season_folder: tplStore.createSeasonFolder,
      conflict_strategy: conflictStrategy.value,
      overrides,
    })
    lastResult.value = res.data
    resultDialog.value = true
    if (!dryRun) {
      await buildPreview()
    }
  } catch (e) {
    showToast('操作失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    executing.value = false
  }
}

watch(
  () => [tplStore.currentTemplate, tplStore.folderTemplate, tplStore.createSeasonFolder],
  () => { if (filesStore.files.length) buildPreview() },
  { deep: true }
)
</script>

<style scoped>
@keyframes slideIn {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}

.source-fade-enter-active {
  transition: opacity 0.22s ease-out, transform 0.22s ease-out;
}
.source-fade-leave-active {
  transition: opacity 0.18s ease-in, transform 0.18s ease-in;
}
.source-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.source-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.modal-enter-active {
  transition: opacity 0.2s ease-out;
}
.modal-enter-active > * {
  transition: opacity 0.2s ease-out, transform 0.22s cubic-bezier(0.22, 1, 0.36, 1);
}
.modal-leave-active {
  transition: opacity 0.15s ease-in;
}
.modal-leave-active > * {
  transition: opacity 0.13s ease-in, transform 0.13s ease-in;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-from > * {
  opacity: 0;
  transform: scale(0.94) translateY(8px);
}
.modal-leave-to > * {
  opacity: 0;
  transform: scale(0.96) translateY(-4px);
}
</style>

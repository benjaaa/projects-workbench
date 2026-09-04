# Beautiful UI — 组件结构提取（照抄素材）

来源：https://www.beautifului.dev/ (MIT License, 亮色主题)

## 设计 Token（亮色）
```
--page:   #fafafb    页面背景
--canvas: #f1f2f3    次级背景
--surface:#fff       卡片表面
--inset:  #f7f8f9    内嵌
--hover:  #f4f5f6    悬停
--hover-2:#e7e9eb
--ink:    #1f2124    主文字
--ink-2:  #62656b    次文字
--ink-3:  #9a9da3    弱文字
--line:   #ecedef    边框
--line-strong:#e0e2e5
--field:  #f2f2f3    输入框
--accent: #0285ff    品牌蓝
--accent-ink:#0170dd
--accent-tint:#e9f3ff
--green:  #189a4d / --green-tint:#e8f5ed
--orange: #ef720c / --orange-tint:#fdf1e5
--red:    #e3474c / --red-tint:#fcecec
--radius-card:10px --radius-chip:6px --radius-control:8px --radius-xl:.75rem
--shadow-hairline: 0 0 0 1px var(--line)
--shadow-card: 0 0 0 1px var(--line),0 1px 2px #1018280a,0 2px 6px #10182808
--shadow-raised: 0 0 0 1px var(--line),0 2px 10px #0000000b
--shadow-overlay: 0 0 0 1px var(--line-strong),0 8px 28px #0001
--shadow-btn: 0 0 0 1px var(--line-strong),0 1px 2px #1018280d
```

## 01 Task Rows（任务状态行）— 对应工作台"任务卡片"
结构（每行）：
```
<div class="flex h-11 w-full items-center gap-2.5 px-2.5 text-left transition-colors duration-100 hover:bg-inset">   ← 行
  <div class="flex size-6 shrink-0 items-center justify-center">                        ← 左侧图标区
    [状态圆图标: size-5.5 rounded-full bg-green 白字 ✓]
  </div>
  <div class="min-w-0 flex-1 truncate text-[13px] font-medium text-ink">Verified vendor records</div>   ← 标题(13px medium)
  <div class="text-[12.5px] text-ink-2 tabular-nums">12 suppliers</div>                ← 副文本(12.5px tabular)
  <span class="inline-flex h-5.5 items-center rounded-full bg-green-tint px-2 text-[11.5px] font-medium text-green">Completed</span>  ← 状态chip
  <div class="-ml-2 flex size-7 shrink-0 items-center justify-center rounded-full text-ink-3">▸</div>    ← 展开箭头
</div>
展开详情:
<div class="grid transition-[grid-template-rows,opacity] duration-300">  ← 手风琴
  <div class="overflow-hidden">
    <div class="mb-2.5 grid grid-cols-[24px_1fr] gap-2.5 px-2.5">        ← 进度行
      <div class="mx-auto h-full w-px bg-line"></div>                    ← 左侧竖线
      <div class="flex flex-col gap-1.5">
        <div class="flex items-center justify-between">                  ← 步骤行: 名称+数值
          <span class="text-[12px] text-ink-2">Matched tax and contact IDs</span>
          <span class="font-mono text-[11.5px] text-ink-3 tabular-nums">12/12</span>
        </div>
```
容器：`self-stretch overflow-hidden rounded-card bg-surface shadow-card`

## 04 Approval Card（确认卡）— 对应工作台"待人为确认"
```
<div class="flex min-h-[196px] w-full max-w-80 flex-col items-stretch">
  <div class="w-full self-start overflow-hidden rounded-card bg-surface shadow-card">
    <div class="primitive-card-pad">                                     ← padding: 16px
      <div class="flex items-start justify-between gap-3">               ← 标题行
        <div class="mt-2 flex flex-col gap-0.5">
          [主标题]  [副标题]
        </div>
        [右上角图标]
      </div>
    </div>
    <div class="primitive-card-footer flex items-center justify-between">  ← 底部: 选项chips + 操作
```
选项 chip（approval 选项）：
```
[三选一 chips: Three (core line) / Five (full case) / Just one hero]
[操作按钮: Alternatives | Accept]
```

## 06 Task Rows 状态徽章样式
```
<span class="inline-flex h-5.5 items-center rounded-full bg-green-tint px-2 text-[11.5px] font-medium text-green">Completed</span>
```
- 高 22px（h-5.5）rounded-full
- 背景 = 状态tint（bg-green-tint）
- 文字 = 状态主色（text-green）11.5px medium
- 语义: Completed=green / 进行中=running(spinner蓝) / failed=red

## 11 Diff Table（差异表格）— 对应工作台"对比展示"
```
<div class="relative overflow-hidden rounded-card bg-surface shadow-card">
  <div class="primitive-card-bar flex items-center justify-between border-b border-line">   ← 卡片头
  [表格]
  <div class="grid grid-cols-[34%_30%_36%] items-center border-t border-line">
```

## 12 Records Table（CRM 表格）— 对应工作台"会话列表/数据列表"
```
表头: <div class="grid grid-cols-[...] border-b border-line px-3 py-2 text-[11.5px] font-medium text-ink-2 uppercase tracking-wide">
行:   <div class="grid grid-cols-[...] items-center border-b border-line px-3 py-2.5">
  [首字母徽章: A 圆底]  [公司名 text-ink 13px]  [标签 chips: bg-ink-tint text-ink-2 rounded-full]  [日期 text-ink-2 12px]  [连接强度 chip]  [链接 text-accent]
表尾: <div class="px-3 py-2 text-[11.5px] text-ink-3"> 26 count · Add calculation · 44% average · 19 links </div>
```

## 13 Filter Table（筛选表格）— 对应工作台"任务列表/筛选"
```
<div class="-mx-1 mb-1 flex items-center gap-1 overflow-x-auto px-1 py-1">   ← 筛选chips行
  [chip: flex h-6.5 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-[12px] font-medium]
  [chip 内点: size-1.5 rounded-full]
  [选中态: bg-ink text-white | 未选: bg-transparent text-ink-2]
<div class="overflow-x-auto rounded-card bg-surface shadow-card">            ← 表格容器
  <div class="min-w-[420px]">
    <div class="grid grid-cols-[1.3fr_0.6fr_0.95fr_0.9fr] border-b border-line px-3 py-2 text-[11.5px] font-medium text-ink-2">   ← 表头
      Task name | Date | Status | Advisor
    <div class="grid grid-cols-[1.3fr_0.6fr_0.95fr_0.9fr] items-center border-b border-line px-3 py-2.5">  ← 数据行
      [任务名 text-ink 13px]  [日期 text-ink-2 12px]  [状态chip]  [Advisor text-ink-2 12px]
```
状态chip: `inline-flex h-5 items-center rounded-full bg-<tint> px-2 text-[11px] font-medium text-<color>`
- To do = bg-transparent border border-line text-ink-2
- In Progress = bg-blue-tint text-accent
- Completed = bg-green-tint text-green

## 14 Sidebar Nav（侧边导航）
```
WORKSPACE 分组标题: text-[11px] font-medium uppercase tracking-wide text-ink-3
导航项: flex items-center gap-2 rounded-control px-2 py-1.5 text-[13px] text-ink-2 hover:bg-hover hover:text-ink
  激活态: bg-hover text-ink font-medium
  [icon] [label] [计数徽章: ml-auto inline-flex h-4.5 items-center rounded-full bg-ink text-white px-1.5 text-[10.5px] font-medium tabular-nums]
Creamery Ops 品牌头: [字母徽章 size-7 rounded-control bg-accent text-white] [名称]
New task 按钮: flex items-center gap-1.5 rounded-control bg-accent text-white px-3 py-1.5 text-[13px] font-medium
```

## 15 Search（命令搜索）
```
[搜索框: rounded-control bg-field px-3 py-2.5 text-[13px] placeholder:text-ink-3]
[结果列表: 每项 flex items-center gap-2.5 px-3 py-2.5 rounded-control hover:bg-hover]
空状态: 居中图标 + text-[13px] text-ink-3 "No results"
```

## 16 Insight Cards（洞察卡片）— 对应工作台"项目卡片/统计卡片"
```
<div class="min-h-[278px] rounded-card bg-surface p-3 shadow-hairline">   ← 卡片(278px)
  <div class="flex items-center gap-4">
    <div class="flex-1">  ← 大数字区
      [标签 text-ink-2 12px]
      [数值 text-3xl font-semibold text-ink tabular-nums]
      [说明 text-ink-3 12px]
    </div>
    <div class="flex-1">  ← 迷你图表
      <div class="mt-2 overflow-hidden rounded-control bg-inset shadow-hairline">
        <div class="flex items-center justify-between border-b border-line px-2.5 py-1.5">  ← 图表头
        <div class="insight-chart-stage relative h-[166px]">  ← 图表区
```

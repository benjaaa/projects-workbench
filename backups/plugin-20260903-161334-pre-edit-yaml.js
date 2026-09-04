// projects-workbench — 全新设计语言（Linear / 现代 SaaS 风格）
// 纯白为底、层级靠留白与字重、圆角更大、阴影更软、着色徽章、分段式标签页、深色 Toast
import { jsx, jsxs, Fragment } from 'react/jsx-runtime'
import { useState, useEffect, useRef } from 'react'
import { cn, host, ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA, KEYBINDS_AREA, Codicon } from '@hermes/plugin-sdk'

var ROUTE = '/projects', SCRIPT = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/obsidian-task.py', PROOT = '2. Project/2.1 Project', VAULT = '/Users/ben/Documents/Second Brain/Second Brain'
// 吉祥物 SVG 资源目录（file:// 绝对路径，img 直接加载）
var ASSET_DIR = 'file:///Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/assets/'
// 冷启动默认首页：应用启动时 hash 为空 → 自动导航到项目工作台（标志位防热重载重复触发）
var _booted = false
// ─── 侧边栏 Issues 图标：对焦框（四角 L 形 + 中心实心点）──────────────
// Hermes 侧边栏导航图标仅接受 codicon 字体字形名，无自定义 SVG 入口；
// 故注册私有 codicon 名 `issues-focus`，并用 CSS mask 以当前文本色绘制原图样式。
var _focusFrameSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.24 3.72H5.92a2.2 2.2 0 0 0-2.2 2.2v3.32"/><path d="M14.76 3.72h3.32a2.2 2.2 0 0 1 2.2 2.2v3.32"/><path d="M20.28 14.76v3.32a2.2 2.2 0 0 1-2.2 2.2h-3.32"/><path d="M9.24 20.28H5.92a2.2 2.2 0 0 1-2.2-2.2v-3.32"/><circle cx="12" cy="12" r="2" fill="black" stroke="none"/></svg>'
var _focusFrameUri = 'data:image/svg+xml,' + encodeURIComponent(_focusFrameSvg)
function _installIssuesFocusIcon() {
  if (typeof document === 'undefined' || !document.head) return
  var st = document.createElement('style')
  st.setAttribute('data-pw', 'issues-focus-icon')
  st.textContent = '.codicon-issues-focus::before{content:"";display:inline-block;width:1em;height:1em;background:currentColor;-webkit-mask:url("' + _focusFrameUri + '") center / contain no-repeat;mask:url("' + _focusFrameUri + '") center / contain no-repeat;}'
  document.head.appendChild(st)
}
_installIssuesFocusIcon()

// ─── 视图切换私有图标（RoundBtn 内 Codicon 用）──────────────
// Hermes codicon 字体无看板/列表可用字形（无效字形不渲染＝按钮无 icon），
// 沿用 issues-focus 的 CSS mask 私有 codicon 方案：
// pw-board=看板（三竖列），pw-list=列表（行+行首标记点）。
var _pwIconSvgs = {
  'pw-board': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="black" stroke="none"><rect x="2" y="2" width="3.4" height="12" rx="1.1"/><rect x="6.3" y="2" width="3.4" height="8.5" rx="1.1"/><rect x="10.6" y="2" width="3.4" height="10" rx="1.1"/></svg>',
  'pw-list': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="black" stroke="none"><circle cx="3" cy="4" r="1.3"/><rect x="5.6" y="3.2" width="8.4" height="1.6" rx="0.8"/><circle cx="3" cy="8" r="1.3"/><rect x="5.6" y="7.2" width="8.4" height="1.6" rx="0.8"/><circle cx="3" cy="12" r="1.3"/><rect x="5.6" y="11.2" width="8.4" height="1.6" rx="0.8"/></svg>',
}
function _installPwViewIcons() {
  if (typeof document === 'undefined' || !document.head) return
  var st = document.createElement('style')
  st.setAttribute('data-pw', 'pw-view-icons')
  var css = ''
  Object.keys(_pwIconSvgs).forEach(function(name) {
    var uri = 'data:image/svg+xml,' + encodeURIComponent(_pwIconSvgs[name])
    css += '.codicon-' + name + '::before{content:"";display:inline-block;width:1em;height:1em;background:currentColor;-webkit-mask:url("' + uri + '") center / contain no-repeat;mask:url("' + uri + '") center / contain no-repeat;}'
  })
  st.textContent = css
  document.head.appendChild(st)
}
_installPwViewIcons()

// ─── Agent 导航图标：整体顺时针旋转 45°（朝向右上/东北，更动感）──────
// robot codicon 同时被侧边栏「新建会话」复用（sidebar/index.tsx SIDEBAR_NAV），
// 不能全局旋转 .codicon-robot；以 data-tour 后缀精确锁定本插件 nav-agent 项。
function _installAgentNavRotate() {
  if (typeof document === 'undefined' || !document.head) return
  var st = document.createElement('style')
  st.setAttribute('data-pw', 'agent-nav-rotate')
  st.textContent = '[data-slot="context-menu-trigger"]:has(> [data-tour="sidebar-nav-projects-workbench:nav-agent"]) > .codicon-robot{transform:rotate(-35deg)}'
  document.head.appendChild(st)
}
_installAgentNavRotate()
export default {
  id: 'projects-workbench', name: 'Work Station',
  register: function(ctx) {
    // 路由化：四个导航入口 + 四个页面（Chat / Inbox / Projects / Issues）
    var VIEWS = [
      { nav: 'nav-agent',   route: '/agent',   view: 'chat',     label: 'Agent',    codicon: 'robot',    actionId: 'workstation.navAgent',   kbd: '6' },
      { nav: 'nav-drafts',   route: '/drafts',   view: 'inbox',    label: 'Drafts',   codicon: 'inbox',    actionId: 'workstation.navDrafts',  kbd: '7' },
      { nav: 'nav-projects', route: '/projects', view: 'projects', label: 'Projects', codicon: 'project',  actionId: 'workstation.navProjects', kbd: '8' },
      { nav: 'nav-issues',   route: '/issues',   view: 'issues',   label: 'Issues',   codicon: 'issues-focus', actionId: 'workstation.navIssues',  kbd: '9' },
    ]
    VIEWS.forEach(function(v) {
      // 导航条 label：名称 + 行尾浅灰快捷键（⌘⇧N，与内置 New Session 的 ⌘N 风格一致）
      // 核心 SidebarNavContribution.label 为 string、label span 是 shrink-to-fit（不撑满行宽）；
      // 以 React 元素渲染，快捷键用 absolute 定位锚到 SidebarMenuItem（relative）实现最右对齐。
      var hint = '\u2318\u21e7' + v.kbd
      var navLabel = jsxs('span', { children: [
        jsx('span', { children: v.label }),
        jsx('span', { style: { position: 'absolute', right: '8px', top: '50%', transform: 'translateY(-50%)', color: FAINT, fontSize: '0.75rem' }, children: hint }),
      ] })
      ctx.register({ id: v.nav, area: SIDEBAR_NAV_AREA, data: { path: v.route, label: navLabel, codicon: v.codicon } })
      ctx.register({ id: 'page-' + v.view, area: ROUTES_AREA, data: { path: v.route }, render: function() { return jsx(App, { initialView: v.view }) } })
      // 应用内快捷键：⌘⇧6/7/8/9 → 分别导航 Agent/Drafts/Projects/Issues
      ctx.register({ id: 'kbd-' + v.view, area: KEYBINDS_AREA, data: { id: v.actionId, category: 'navigation', defaults: ['mod+shift+' + v.kbd], label: 'Work Station: ' + v.label, run: function() { host.navigate(v.route) } } })
    })
    ctx.register({ id: 'palette', area: PALETTE_AREA, data: { label: 'Work Station', codicon: 'project' }, action: function() { host.navigate('/agent') } })
    // 冷启动默认首页：应用启动时 hash 为空或为默认 chat 路由 → 自动导航到 Chat 首页
    // （切换默认 profile 后启动 hash 可能是 #/，仍应进入工作台；标志位防热重载重复触发）
    if (!_booted) {
      var _h = (window.location.hash || '').replace(/^#/, '')
      var _isDefault = !_h || _h === '/' || _h === '/chat' || _h.indexOf('/chat') === 0
      if (_isDefault) {
        _booted = true
        setTimeout(function() { host.navigate('/agent') }, 0)
      }
    }
  }
}

// ─── Data layer (unchanged) ──────────────────────────────
function sh(cmd, retries) {
  if (retries === undefined) retries = 6
  return host.request('shell.exec', { command: cmd, timeout: 90000 }).then(function(r) { if (r.code !== 0) throw new Error((r.stderr || '').slice(0, 200)); return r.stdout })
    .catch(function(e) {
      var m = (e && (e.message || e.error)) ? (e.message || e.error) : String(e || '')
      if (retries > 0 && /gateway (unavailable|is not connected)/i.test(m)) {
        return new Promise(function(res) { setTimeout(res, 500) }).then(function() { return sh(cmd, retries - 1) })
      }
      throw e
    })
}
function b64d(s) { var b = String(s || '').trim().replace(/ /g, '+'); var bin = atob(b); var bytes = new Uint8Array(bin.length); for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i); return new TextDecoder('utf-8').decode(bytes) }
function jp(o) { var s = b64d(o); return JSON.parse(s) }
function ld(retries) {
  if (retries === undefined) retries = 3
  return sh('env HOME=/Users/ben python3 ' + SCRIPT + ' save').then(function(o) {
    var info = JSON.parse(o); var total = info.len; var pid = info.pid || ''; var chunks = []
    for (var i = 0; i < total; i += 3900) chunks.push(i)
    return Promise.all(chunks.map(function(off) {
      return sh('env HOME=/Users/ben python3 ' + SCRIPT + ' read ' + off + ' 3900 ' + pid).then(function(c) { return c.trim() })
    })).then(function(parts) { return jp(parts.join('')) })
  }).catch(function(e) {
    if (retries > 0) return new Promise(function(res) { setTimeout(res, 800) }).then(function() { return ld(retries - 1) })
    throw e
  })
}
function b64u(s) { return btoa(unescape(encodeURIComponent(s))) }
// 友好错误：识别 Obsidian 未连接/脚本失败，返回易读提示（避免一坨 Traceback）
function friendlyErr(e) {
  var m = (e && (e.message || e.error) ? (e.message || e.error) : String(e || '')).toString()
  var low = m.toLowerCase()
  if (low.indexOf('traceback') >= 0 || low.indexOf('obsidian') >= 0 || low.indexOf('eval') >= 0 ||
      low.indexOf('timed out') >= 0 || low.indexOf('refused') >= 0 || low.indexOf('not found') >= 0 ||
      low.indexOf('no such file') >= 0 || low.indexOf('connection') >= 0 || low.indexOf('unable') >= 0) {
    return '请先打开 Obsidian（确保已完全加载），然后点击右上角刷新重试'
  }
  return (m || '操作失败').slice(0, 120)
}
function runSpec(spec) {
  var b = b64u(JSON.stringify(spec))
  return sh('env HOME=/Users/ben python3 ' + SCRIPT + ' run "' + b + '"').then(function(o) {
    var r = jp(o)
    // 大输出分片：脚本输出 __chunked 元信息时，分片读取临时文件（每片 3000，避开 Hermes shell.exec 截断）
    if (r && r.__chunked) {
      var pid = r.pid || '', len = r.len || 0, parts = [], off = 0
      function readChunk() {
        return sh('env HOME=/Users/ben python3 ' + SCRIPT + ' read ' + off + ' 3000 ' + pid).then(function(c) {
          parts.push(c.trim())
          off += 3000
          if (off < len) return readChunk()
          return jp(parts.join(''))
        })
      }
      return readChunk()
    }
    if (!r.ok) throw new Error(r.error || 'op failed')
    return r
  })
}
function editLog(path, idx, text) { return runSpec({ op: 'edit_log', path: path, idx: idx, text: text }) }

// ─── Maps ────────────────────────────────────────────────
var ST = { open: '待办', 'In-Progress': '进行中', Waiting: '等待中', Done: '已完成', Dropped: '已取消' }
var PR = { p0: 'P0', p1: 'P1', p2: 'P2' }
var SN = { open: 'In-Progress', 'In-Progress': 'Waiting', Waiting: 'Done', Done: 'Dropped', Dropped: 'open' }
var PN = { p0: 'p1', p1: 'p2', p2: 'p0' }
var PST = { open: '待办', 'In-Progress': '进行中', Waiting: '等待中', Routine: '常态化', Agent: '托管给Agent', Review: '待人为确认', Done: '已完成', Dropped: '已取消' }

// ─── Design tokens (Beautiful UI light theme 2026-08-12) ──
var INK = '#1f2124', BODY = '#62656b', MUT = '#9a9da3', FAINT = '#b8bbc1'
var LINE = '#ecedef', LINE2 = '#e0e2e5', SBG = '#f1f2f3'
var ACC = '#0285ff', ACCD = '#0170dd', ACCS = '#e9f3ff'
var SURF = '#fff', HOV = '#f4f5f6', FIELD = '#f2f2f3', INSET = '#f7f8f9'
var GREEN = '#189a4d', GREEN_T = '#e8f5ed', ORANGE = '#ef720c', ORANGE_T = '#fdf1e5', RED = '#e3474c', RED_T = '#fcecec'
var PAGE = '#ffffff'
// ─── Token 扩充（2026-08-31 收敛硬编码）──
// 控件色
var BTN = '#4a4a4d'          // 主按钮底（用户确认的深灰，非黑非蓝）
var IN_BRD = '#d5d5d8'       // 输入框/复选框边框
var FOCUS_BRD = '#b0b0b4'    // 输入框 focus 边框（灰，非蓝——用户确认约定）
var DIVIDER = '#f0f0f0'      // 分隔线（模态 footer/header、菜单分割）
// 危险色（任务删除/逾期强调，区别于状态 RED）
var DANGER = '#c0392b'
var DANGER_T = '#fdecec'
// 来源标签紫（kanban）
var PURPLE = '#8b5cf6'
var PURPLE_T = '#f3edfe'
// 来源标签橙（cron），与警告 ORANGE 同值但角色不同——收敛期保持独立命名
var CRON_ORANGE = ORANGE
var CRON_ORANGE_T = ORANGE_T
// 分段控件/开关等组件局部色（收敛自散落硬编码）
var SEG_OFF = '#f2f2f4'      // 分段 tab 未选中底
var DOT_OFF = '#e3e3e7'      // 轮播指示点未选中
var DOT_ON = '#b6b6bd'       // 轮播指示点选中
var TRACK_OFF = '#d9d9de'    // 开关轨道未选中
var GRAY_DOT = '#999999'     // Dropped 状态点
var OPEN_DOT = '#c6c6cd'     // open 状态点/滚动条 thumb
// 高频软阴影（按钮/悬浮小卡）
var SH_SOFT = '0 1px 2px rgba(16,24,40,0.06)'
// 阴影：1px 边框 + 极浅阴影（Beautiful UI 风格）
var SH_CARD = '0 0 0 1px #ecedef, 0 1px 2px rgba(16,24,40,0.04), 0 2px 6px rgba(16,24,40,0.03)'
var SH_RAISED = '0 0 0 1px #ecedef, 0 2px 10px rgba(0,0,0,0.04)'
var SH_HAIR = '0 0 0 1px #e0e2e5'
var SH_BTN = '0 0 0 1px #e0e2e5, 0 1px 2px rgba(16,24,40,0.05)'

// 状态点 / 状态徽章（着色软底）
var SDOT = { open: OPEN_DOT, 'In-Progress': ACC, Waiting: ORANGE, Agent: PURPLE, Review: ORANGE, Done: GREEN, Dropped: GRAY_DOT }
var SBGC = {
  open: { background: HOV, color: BODY },
  'In-Progress': { background: ACCS, color: ACC },
  Waiting: { background: ORANGE_T, color: ORANGE },
  Agent: { background: PURPLE_T, color: PURPLE },
  Review: { background: ORANGE_T, color: ORANGE },
  Done: { background: GREEN_T, color: GREEN },
  Dropped: { background: HOV, color: MUT },
}
// 优先级徽章
var PBGC = {
  p0: { background: RED_T, color: RED },
  p1: { background: ORANGE_T, color: ORANGE },
  p2: { background: HOV, color: BODY },
}
// 项目状态点
var PJDOT = { open: OPEN_DOT, 'In-Progress': ACC, Waiting: ORANGE, Routine: PURPLE, Agent: PURPLE, Review: ORANGE, Done: GREEN, Dropped: GRAY_DOT }

// ─── Helpers ─────────────────────────────────────────────
function dL(d) { if (!d) return ''; if (d === 'today') return '今天'; if (d === 'overdue') return '已逾期'; if (d === 'week') return '本周'; return d }
function todayLocal() { var d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0') }
// 今天起 n 天后的日期串（YYYY-MM-DD）——Issues 默认筛选「近7天」等使用
function addDaysLocal(n) { var d = new Date(); d.setDate(d.getDate() + n); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0') }
// 卡片左侧强调标记：今天到期或已逾期（未完成/未取消的任务才强调）
function dueFlag(t, today) { return !!(t.due && t.due <= today && t.status !== 'Done' && t.status !== 'Dropped') }
function dot(color, size) { return jsx('span', { style: { width: size || 7, height: size || 7, borderRadius: 99, background: color, flexShrink: 0, display: 'inline-block' } }) }
// 重复任务标签：从 frontmatter repeat 字段生成易读文字（如"每2周·周二"）
function repLabel(t) {
  var unit = t.repeat_unit || '', every = t.repeat_every || '1', day = t.repeat_day || ''
  var W = ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日']
  if (unit === 'day') return '每' + every + '天'
  if (unit === 'week') return '每' + (every === '1' ? '' : every) + '周' + (day ? '·' + (W[parseInt(day, 10)] || '') : '')
  if (unit === 'month') return '每' + (every === '1' ? '' : every) + '月' + (day ? '·' + day + '号' : '')
  return '重复'
}
// Beautiful UI 风格 chip：h-5.5(22px) rounded-full bg-<tint> px-2 text-[11.5px] font-medium
function buiChip(color, tint, text, cls) {
  return jsx('span', { className: (cls || '') + ' inline-flex shrink-0 items-center rounded-full px-2', style: { height: '22px', background: tint, color: color, fontSize: '11.5px', fontWeight: 500, lineHeight: '22px', whiteSpace: 'nowrap' }, children: text })
}

// 圆形 icon 按钮原语：圆形、灰外框、透明底（hover 浅灰）；过滤/视图切换等圆按钮统一走这里，保证效果一致
// hover 统一走 pw-hover CSS（见 _installPwUiCss），不再手写 onMouseEnter/Leave
function RoundBtn(props) {
  return jsx('span', {
    title: props.title, onClick: props.onClick,
    className: 'inline-flex items-center justify-center cursor-pointer select-none shrink-0 transition-colors duration-150 pw-roundbtn' + (props.active ? ' is-active' : ''),
    style: { width: '28px', height: '28px', borderRadius: 99, border: '1.5px solid ' + LINE2, background: props.active ? HOV : 'transparent', color: props.active ? INK : MUT },
    children: props.children,
  }, props.rkey)
}

// ═══ 共享看板原语（BoardView / ProjectDetail 唯一事实源）═══════════
// 统一 hover 样式（pw-hover=背景 hover 浅灰；pw-roundbtn=圆按钮 active/hover 态）
function _installPwUiCss() {
  if (typeof document === 'undefined' || !document.head) return
  if (document.querySelector('style[data-pw="pw-ui-hover"]')) return
  var st = document.createElement('style')
  st.setAttribute('data-pw', 'pw-ui-hover')
  st.textContent = '[data-pw] .pw-hover{transition:background-color .15s}[data-pw] .pw-hover:hover{background:' + HOV + '}'
    + '[data-pw] .pw-hover-faint{transition:background-color .15s,color .15s}[data-pw] .pw-hover-faint:hover{background:' + FIELD + ';color:' + INK + '}'
    + '[data-pw] .pw-hover-acc{transition:color .15s}[data-pw] .pw-hover-acc:hover{color:' + ACC + '}'
    + '[data-pw] .pw-roundbtn:hover{background:' + HOV + ';color:' + INK + '}'
    + '[data-pw] .pw-plus-btn:hover{background:' + SBG + ' !important}'
    + '[data-pw] .pw-taskcard{transition:transform .15s,box-shadow .15s}[data-pw] .pw-taskcard:hover{transform:translateY(-1px);box-shadow:0 0 0 1px ' + LINE + ',0 4px 12px rgba(16,24,40,0.08)}'
    + '[data-pw] .pw-board-col.is-dragover{box-shadow:inset 0 0 0 2px ' + ACC + ';background:' + ACCS + '}'
  document.head.appendChild(st)
}
_installPwUiCss()

// 看板列状态分组（Issues 全局看板与项目详情看板共用）
// Agent+Review 合并一列（托管流程：agent 执行中 + 完成待确认为同一流程）；拖入该列落为 Agent（Review 仅由 worker 完成触发，不手动设置）
var BOARD_GROUPS = [
  { status: 'open', label: '待办' },
  { status: 'In-Progress', label: '进行中' },
  { status: 'Waiting', label: '等待中' },
  { status: 'Agent', label: '托管给Agent', match: ['Agent', 'Review'] },
  { status: 'Done', label: '已完成/取消', match: ['Done', 'Dropped'] },
]

// 任务卡片（唯一实现；variant 'project' 时行2 带产出数、行3 仅处理人不带项目名）
// 视觉：白底发丝边 + hover 微上浮；仅逾期/今日到期任务左侧 2px 红色 border 标识，其余无外框色
function TaskCard(props) {
  var t = props.t, R = props.R, today = props.today
  var overdue = dueFlag(t, today)
  return jsxs('div', {
    className: 'cursor-pointer transition-all duration-150 pw-taskcard',
    style: { borderRadius: '5px', padding: '9px 12px', background: SURF, boxShadow: SH_HAIR, borderLeft: overdue ? '2px solid ' + DANGER : 'none' },
    draggable: true,
    onDragStart: function(e) { e.dataTransfer.setData('text/plain', t.path); e.dataTransfer.effectAllowed = 'move'; e.currentTarget.style.opacity = '0.4' },
    onDragEnd: function(e) { e.currentTarget.style.opacity = '1' },
    onClick: function() { R.setDw(t); R.setVw('task-detail') },
    children: [
      // 行1：标题（列已按状态分类，无需状态chip）+ Review 状态点（合并列内区分待验收）+ 重复标记
      jsxs('div', { className: 'flex items-center gap-1', children: [
        t.status === 'Review' ? jsx('span', { title: '待人为确认', style: { width: '6px', height: '6px', borderRadius: 99, background: PURPLE, flexShrink: 0 } }) : null,
        jsx('span', { className: 'text-[0.8125rem] font-medium truncate', style: { color: INK, flex: 1, minWidth: 0, letterSpacing: '-0.005em' }, children: t.title }),
        t.repeat_mode ? jsx('span', { title: '重复周期任务：' + repLabel(t), style: { color: MUT, flexShrink: 0, fontSize: '11px' }, children: '🔁' }) : null,
      ]}),
      // 行2：优先级 + 截止/完成日期（+ 项目视图产出数）
      jsxs('div', { className: 'flex items-center gap-1.5 mt-1.5', children: [
        buiChip(PBGC[t.priority] ? PBGC[t.priority].color : MUT, PBGC[t.priority] ? PBGC[t.priority].background : HOV, PR[t.priority] || t.priority),
        (t.status === 'Done' || t.status === 'Dropped') && t.complete
          ? jsxs('span', { className: 'flex items-center gap-0.5 text-[0.6875rem] tabular-nums', style: { color: MUT }, children: [
              jsx(Codicon, { name: 'calendar', className: 'text-[0.75rem]' }),
              jsx('span', { children: dL(t.complete) }),
            ]})
          : t.due && jsxs('span', { className: 'flex items-center gap-0.5 text-[0.6875rem] tabular-nums', style: { color: overdue ? DANGER : MUT, fontWeight: overdue ? 500 : 400 }, children: [
              jsx(Codicon, { name: 'calendar', className: 'text-[0.75rem]' }),
              jsx('span', { children: dL(t.due) }),
            ]}),
        props.variant === 'project' && (t.output || []).length > 0 && jsxs('span', { className: 'flex items-center gap-0.5 text-[0.6875rem]', style: { color: MUT }, children: [
          jsx(Codicon, { name: 'file', className: 'text-[0.75rem]' }),
          jsx('span', { children: (t.output || []).length }),
        ]}),
      ]}),
      // 行3：处理人（+ 全局视图项目名靠右最多7字符）
      (t.handler || (props.variant !== 'project' && t.project)) ? jsxs('div', { className: 'flex items-center gap-1 mt-1.5', children: [
        jsx(Codicon, { name: 'account', className: 'text-[0.75rem]', style: { color: MUT } }),
        jsx('span', { className: 'text-[0.6875rem]', style: { color: MUT }, children: t.handler }),
        props.variant !== 'project' && jsx('span', { className: 'text-[0.6875rem]', style: { marginLeft: 'auto', color: FAINT, maxWidth: '7em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, children: (t.project || t.dir || '') }),
      ]}) : null,
    ],
  }, t.path)
}

// 看板列（唯一实现）：列退成浅灰底 + 发丝边，列头小字标签；卡片列表 + 拖拽投放（拖拽高亮走 is-dragover class）
function BoardColumn(props) {
  var g = props.g, R = props.R, today = props.today, tasks = props.tasks
  return jsxs('div', { className: 'flex flex-col min-h-[80px] shrink-0 pw-board-col', style: { background: INSET, borderRadius: '6px', outline: '1px solid ' + LINE2, outlineOffset: '-1px', width: '275px', padding: '10px' },
    onDragOver: function(e) { e.preventDefault(); e.currentTarget.classList.add('is-dragover') },
    onDragLeave: function(e) { e.currentTarget.classList.remove('is-dragover') },
    onDrop: function(e) {
      e.preventDefault(); e.currentTarget.classList.remove('is-dragover')
      var path = e.dataTransfer.getData('text/plain')
      if (!path) return
      var t = (props.dropSource || tasks).filter(function(x) { return x.path === path })[0]
      if (t && t.status !== g.status) R.doSetField(t, 'status', g.status, true)
    },
    children: [
      // 列头：状态点 + 小字大写标签 + 计数（弱化，靠列内卡片为主体）
      jsxs('div', { className: 'flex items-center gap-1.5', style: { height: '24px', padding: '0 2px', marginBottom: '8px' }, children: [
        dot(SDOT[g.status], 6),
        jsx('span', { style: { fontSize: '0.6875rem', fontWeight: 600, color: BODY, letterSpacing: '0.02em' }, children: g.label }),
        jsx('span', { className: 'ml-auto text-[0.6875rem] tabular-nums', style: { color: FAINT }, children: tasks.length }),
      ]}),
      jsx('div', { className: 'flex flex-col', style: { gap: '6px' }, children: tasks.length === 0
        ? jsx('div', { className: 'rounded-[4px] border border-dashed py-5 text-center text-[0.6875rem]', style: { color: FAINT, borderColor: LINE2 }, children: '—' })
        : tasks.map(function(t) { return jsx(TaskCard, { t: t, R: R, today: today, variant: props.variant, key: t.path }) }),
      }),
    ]}, g.status)
}

// ─── Main component ──────────────────────────────────────
function App(props) {
  var R = useReducer(props && props.initialView)
  if (R.vw === 'project' && R.sel) return jsx(ProjectDetail, R)
  if (R.vw === 'chat') return jsx(ChatPage, R)
  if (R.vw === 'issues') return jsx(IssuesPage, R)
  if (R.vw === 'inbox') return jsx(InboxList, R)
  if (R.vw === 'inbox-detail') return jsx(InboxDetail, R)
  if (R.vw === 'task-detail' && R.dw) return jsx(TaskDetailPage, R)
  return jsx(ProjectsPage, R)
}

// ─── 页面：Chat 首页（ChatHome + 抽屉/弹窗）───────────────
function ChatPage(R) {
  var R2 = Object.assign({}, R, { onExit: function(v) { if (v === 'board' || v === 'issues') host.navigate('/issues'); else if (v === 'projects') host.navigate('/projects'); else host.navigate('/agent') } })
  return jsxs(Fragment, { children: [
    jsx(ChatHome, R2),
    jsx(Modal, R),
    jsx(Toast, R),
  ]})
}

// ─── 页面：Issues 看板 ────────────────────────────────────
function IssuesPage(R) {
  return jsxs(Fragment, { children: [
    jsx('div', { 'data-pw': '1', className: S.page, style: { background: PAGE }, children: jsxs('div', { className: S.wrap, children: [
      jsxs('div', { className: 'flex items-center justify-between', style: { marginBottom: '18px' }, children: [
        jsxs('div', { style: { display: 'flex', alignItems: 'baseline', gap: '10px' }, children: [
          jsx('span', { style: { fontSize: '1.25rem', fontWeight: 600, color: INK, letterSpacing: '-0.01em' }, children: 'Issues' }),
          jsx('span', { style: { fontSize: '0.75rem', color: MUT }, children: R.ts.length + ' 个' }),
        ]}),
        jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' }, children: [
          jsx('span', { className: S.iconBtn, style: { color: MUT }, onClick: R.load, children: jsx(Codicon, { name: 'refresh', className: 'text-[0.9375rem]' }) }),
          jsx(Btn, { onClick: function() { R.setMd('task') }, children: '+ New Issue' }),
        ]}),
      ]}),
      jsx(BoardView, R),
    ]}) }),
    jsx(Modal, R),
    jsx(Toast, R),
  ]})
}

// ─── 页面：Projects 项目列表 ──────────────────────────────
function ProjectsPage(R) {
  var flt = useState('active'), filter = flt[0], setFilter = flt[1]
  var shown = R.ps.filter(function(p) { return fltMatch(filter, p.status) })
  return jsxs(Fragment, { children: [
    jsx('div', { 'data-pw': '1', className: S.page, style: { background: PAGE }, children: jsxs('div', { className: S.wrap, children: [
      jsxs('div', { className: 'flex items-center justify-between', style: { marginBottom: '18px' }, children: [
        jsxs('div', { style: { display: 'flex', alignItems: 'baseline', gap: '10px' }, children: [
          jsx('span', { style: { fontSize: '1.25rem', fontWeight: 600, color: INK, letterSpacing: '-0.01em' }, children: 'Projects' }),
          jsx('span', { style: { fontSize: '0.75rem', color: MUT }, children: R.ps.length + ' 个' }),
        ]}),
        jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' }, children: [
          jsx('span', { className: S.iconBtn, style: { color: MUT }, onClick: R.load, children: jsx(Codicon, { name: 'refresh', className: 'text-[0.9375rem]' }) }),
          jsx(Btn, { onClick: function() { R.setMd('project') }, children: '+ New Project' }),
        ]}),
      ]}),
      jsxs('div', { style: { marginBottom: '14px' }, children: [jsx(StatusFilter, { value: filter, onChange: setFilter })] }),
      R.loading ? jsx(Center, { icon: 'loading', spin: true, text: '加载中…' })
      : R.err ? jsx(Center, { icon: 'error', text: '出错：' + R.err })
      : R.ps.length === 0 ? jsx(Center, { icon: 'project', text: 'No projects yet' })
      : shown.length === 0 ? jsx(Center, { icon: 'project', text: 'No projects match the filter' })
      : jsx('div', { className: 'grid gap-3', style: { gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }, children: shown.map(function(p) {
          var p_ts = R.pts(p.title), done = p_ts.filter(function(x) { return x.status === 'Done' || x.status === 'Dropped' }).length
          return jsxs('div', {
            className: 'cursor-pointer transition-all duration-150 hover:bg-[#f7f8f9]',
            style: { borderRadius: '12px', padding: '16px 18px', background: '#fff', boxShadow: SH_CARD },
            onClick: function() { R.setSel(p.title); R.setVw('project'); R.setTb('inputs'); R.loadSessions(p.dir || p.title).then(R.setSess) },
            children: [
              jsxs('div', { className: 'flex items-center gap-2', children: [
                dot(PJDOT[p.status] || FAINT, 6),
                jsx('span', { className: 'text-[0.9375rem] font-semibold flex-1 min-w-0 truncate', style: { color: INK }, children: p.title }),
                buiChip(MUT, SBG, PST[p.status] || p.status || '进行中'),
                jsx('span', { style: { color: FAINT }, children: jsx(Codicon, { name: 'chevron-right', className: 'text-[0.875rem]' }) }),
              ]}),
              jsx('div', { className: 'text-[0.6875rem] mt-1.5', style: { color: MUT }, children: (p.start || '—') + ' → ' + (p.due || '—') }),
              jsxs('div', { className: 'mt-3 grid grid-cols-2 gap-2.5', children: [
                jsxs('div', { className: 'rounded-[8px]', style: { background: FIELD, padding: '10px 12px' }, children: [
                  jsx('div', { className: 'text-[0.625rem]', style: { color: MUT }, children: '任务完成' }),
                  jsxs('div', { className: 'flex items-baseline gap-1 mt-1', children: [
                    jsx('span', { className: 'text-[1.25rem] font-semibold tabular-nums', style: { color: INK }, children: done }),
                    jsx('span', { className: 'text-[0.6875rem]', style: { color: MUT }, children: '/' + p_ts.length }),
                  ]}),
                ]}),
                jsxs('div', { className: 'rounded-[8px]', style: { background: FIELD, padding: '10px 12px' }, children: [
                  jsx('div', { className: 'text-[0.625rem]', style: { color: MUT }, children: '关联会话' }),
                  jsxs('div', { className: 'flex items-baseline gap-1 mt-1', children: [
                    jsx('span', { className: 'text-[1.25rem] font-semibold tabular-nums', style: { color: INK }, children: (R.sessCounts && R.sessCounts[p.dir || p.title] || 0) + '' }),
                    jsx('span', { className: 'text-[0.6875rem]', style: { color: MUT }, children: '个' }),
                  ]}),
                ]}),
              ]}),
            ],
          }, p.path || p.title)
        }) }),
    ]}) }),
    jsx(Modal, R),
    jsx(Toast, R),
  ]})
}

// ─── Reducer hook (state + actions) ──────────────────────
function useReducer(initialView) {
  var ps = useState([]), ts = useState([]), loading = useState(true), err = useState(null)
  var sel = useState(null), vw = useState(initialView || 'projects'), dw = useState(null), tb = useState('inputs')
  var md = useState(null), ef = useState(null), sess = useState([]), to = useState(null)
  var sc = useState({}), sessCounts = sc[0], setSessCounts = sc[1]
  var tmRef = useRef(null)

  var setPs = ps[1], setTs = ts[1], setLoading = loading[1], setErr = err[1]
  var setSel = sel[1], setVw = vw[1], setDw = dw[1], setTb = tb[1]
  var setMd = md[1], setEf = ef[1], setSess = sess[1], setTo = to[1]

  // 开始时间自动流转：status==='open' 且 start<=今天 → 自动进入 In-Progress（含重复任务）
  // 在创建任务、编辑任务、刷新时都会触发
  function autoStartFlow(taskList) {
    var tasks = taskList || ts[0]
    var todayS = todayLocal()
    var dueStart = tasks.filter(function(t) { return t.status === 'open' && t.start && String(t.start) <= todayS })
    if (!dueStart.length) return Promise.resolve()
    return Promise.all(dueStart.map(function(t) {
      return runSpec({ op: 'set_property', path: t.path, field: 'status', value: 'In-Progress' }).catch(function(e) { console.error('[pw] auto start→inprogress failed:', e) })
    })).then(function() {
      dueStart.forEach(function(t) { logOp(t.project || '', t.title, 'status_change', '「' + (t.project || '') + '」任务「' + t.title + '」到达开始日期，自动进入进行中') })
      return ld().then(function(r2) { setPs(r2.projects || []); setTs(r2.tasks || []) }).catch(function() {})
    })
  }

  function load() {
    setLoading(true); setErr(null)
    ld().then(function(r) {
      var tasks = r.tasks || []
      setPs(r.projects || []); setTs(tasks); pollKanban(tasks)
      autoStartFlow(tasks)
    })
      .catch(function(e) { setErr(friendlyErr(e)); setLoading(false) })
      .finally(function() { setLoading(false) })
    // Load session counts for all projects
    sh('env HOME=/Users/ben python3 ' + SCRIPT + ' session_counts').then(function(o) {
      try { setSessCounts(jp(o)) } catch(e) { console.error('[pw] session_counts parse failed:', e) }
    }).catch(function(e) { console.error('[pw] session_counts failed:', e) })
  }

  function pollKanban(taskList) {
    var tasks = taskList || ts[0]
    var agentTs = tasks.filter(function(x) { return x.status === 'Agent' && x.kanban_task_id })
    if (!agentTs.length) return
    agentTs.forEach(function(t) {
      runSpec({ op: 'kanban_status', task_id: t.kanban_task_id, board: 'default' }).then(function(res) {
        // kanban done = worker 完成 → 任务状态改为 Review（待人为确认）
        if (res && res.status === 'done') {
          runSpec({ op: 'set_property', path: t.path, field: 'status', value: 'Review' }).then(function() {
            // 尝试回写 worker session_id 到任务 frontmatter
            runSpec({ op: 'kanban_worker_session', task_id: t.kanban_task_id, board: 'default' }).then(function(wr) {
              if (wr && wr.worker_session_id) {
                var prev = t.session_ids || ''
                var list = prev ? prev.split(',').filter(Boolean) : []
                if (list.indexOf(wr.worker_session_id) < 0) list.push(wr.worker_session_id)
                runSpec({ op: 'set_property', path: t.path, field: 'session_ids', value: list.join(',') }).catch(function(e) { console.error('[pw] session_ids write failed:', e) })
                // 将 worker session 关联到项目目录（更新 cwd → 支持 resume + AGENTS.md + 项目会话列表）
                runSpec({ op: 'kanban_link_session', task_id: t.kanban_task_id, worker_session_id: wr.worker_session_id, board: 'default' }).catch(function(e) { console.error('[pw] kanban_link_session failed:', e) })
                // 自动写推进记录：kanban worker 完成（YAML schema，跨 agent 可读）
                var now = new Date()
                var p2 = function(n) { return (n < 10 ? '0' : '') + n }
                var logDate = p2(now.getMonth() + 1) + '-' + p2(now.getDate()) + ' ' + p2(now.getHours()) + ':' + p2(now.getMinutes()) + ':' + p2(now.getSeconds())
                var yamlEntry = '- date: ' + logDate + '\n'
                  + '  type: kanban\n'
                  + '  summary: Agent 完成任务，待人为确认\n'
                  + '  sessions:\n'
                  + '    - id: ' + wr.worker_session_id + '\n'
                  + '      source: kanban\n'
                  + '  pending:\n'
                  + '    - 待人为确认\n'
                runSpec({ op: 'read', path: t.path }).then(function(o) {
                  var c = o.content || ''
                  var re = /(## 推进记录\n[\s\S]*?)(\n## |$)/
                  var m = c.match(re)
                  if (m) {
                    var section = m[1]
                    // 检查是否已有 YAML 围栏块
                    var yamlFenceRe = /```yaml\n([\s\S]*?)```/
                    var yamlMatch = section.match(yamlFenceRe)
                    var newSection
                    if (yamlMatch) {
                      // 已有 YAML 块：在块内末尾追加条目
                      var yamlContent = yamlMatch[1].trimEnd()
                      var newYamlContent = yamlContent + '\n' + yamlEntry.trimEnd()
                      newSection = section.replace(yamlFenceRe, '```yaml\n' + newYamlContent + '\n```')
                    } else {
                      // 无 YAML 块：新建围栏块
                      newSection = section.trimEnd() + '\n```yaml\n' + yamlEntry.trimEnd() + '\n```\n'
                    }
                    var newContent = c.replace(re, newSection + m[2])
                    runSpec({ op: 'write', path: t.path, content: newContent }).catch(function(e) { console.error('[pw] auto log write failed:', e) })
                  }
                }).catch(function(e) { console.error('[pw] auto log read failed:', e) })
              }
            }).catch(function(e) { console.error('[pw] kanban_worker_session failed:', e) })
            // 刷新任务列表
            ld().then(function(r) { setPs(r.projects || []); setTs(r.tasks || []) }).catch(function(e) { console.error('[pw] pollKanban refresh failed:', e) })
          }).catch(function(e) { console.error('[pw] status→Review write failed:', e) })
        }
      }).catch(function(e) { console.error('[pw] kanban_status poll failed:', e) })
    })
  }
  useEffect(function() { load() }, [])
  // 定时轮询 kanban 状态（每 60s），检测 worker 完成
  useEffect(function() {
    var timer = setInterval(function() { pollKanban() }, 60000)
    return function() { clearInterval(timer) }
  }, [ts[0]])

  // 当视图切换时，更新文件浏览器路径
  useEffect(function() {
    var curVw = vw[0], curSel = sel[0]
    var cwd = VAULT + '/' + PROOT
    if (curVw === 'project' && curSel) {
      var pjn = pj(curSel)
      if (pjn) cwd = VAULT + '/' + PROOT + '/' + (pjn.dir || pjn.title)
    }
    try { host.state.cwd.set(cwd) } catch(e) { console.error('[pw] host.state.cwd.set failed:', e) }
  }, [vw[0], sel[0]])

  useEffect(function() {
    function onKey(ev) {
      if (ev.key !== 'Escape') return
      if (md[0]) setMd(null)
      else if (dw[0]) setDw(null)
    }
    window.addEventListener('keydown', onKey)
    return function() { window.removeEventListener('keydown', onKey) }
  }, [md[0], dw[0]])

  function pts(proj) { return ts[0].filter(function(x) { return x.project === proj || x.dir === proj || x.project === (pj(proj) || {}).dir || x.dir === (pj(proj) || {}).title }) }
  function pj(n) { return ps[0].filter(function(p) { return p.title === n || p.dir === n || (p.path && p.path.indexOf('/' + n + '/') >= 0) })[0] }
  function tost(m) { setTo(m); clearTimeout(tmRef.current); tmRef.current = setTimeout(function() { setTo(null) }, 2500) }

  function updateSection(path, sec, text) { return runSpec({ op: 'update_section', path: path, section: sec, text: text }) }
  function toggleAc(path, idx) { return runSpec({ op: 'toggle_ac', path: path, idx: idx }) }

  function logOp(project, task, action, detail) {
    // 操作日志（SQLite）——不阻塞主流程
    runSpec({ op: 'ops_log', project: project || '', task: task || '', action: action || '', detail: detail || '' }).catch(function(e) { console.error('[pw] ops_log failed:', e) })
  }
  function doCreateProj() {
    var dir = document.getElementById('npName').value.trim(); if (!dir) { tost('请输入项目名称'); return }
    var bg = document.getElementById('npBg').value.trim(), goal = document.getElementById('npGoal').value.trim()
    var today = todayLocal()
    var due = document.getElementById('npDue') ? document.getElementById('npDue').value : ''
    var pC = '---\ntitle: ' + dir + '\nstatus: open\nstart: ' + today + (due ? '\ndue: ' + due : '') + '\ntags:\n  - project\n---\n\n# ' + dir + '\n\n## 项目背景\n' + bg + '\n\n## 项目目标\n' + goal + '\n'
    var aC = '# 项目：' + dir + '\n\n## 项目简介\n\n## 项目规范（必须遵守）\n1. 文件存放：用户输入文件 → `raw/`；Agent最终任务交付物 → `output/`；脚本 → `scripts/`；Agent过程产物（数据、过程性文档等）→ `tmp/`\n2. 涉及项目、任务的创建、修改等行为，严格按照 `projects-workbench` skill 执行\n\n<!-- TASK SNAPSHOT START -->\n## 当前任务状态（自动维护）\n（暂无任务）\n<!-- TASK SNAPSHOT END -->\n'
    runSpec({ op: 'create_project', dir: PROOT + '/' + dir, project_content: pC, agents_content: aC })
      .then(function() { setMd(null); load(); tost('已创建项目「' + dir + '」'); logOp(dir, '', 'create_project', '创建项目「' + dir + '」') })
      .catch(function(e) { setErr(friendlyErr(e)) })
  }
  function doCreateTask() {
    try {
    var title = document.getElementById('ntTitle').value.trim(); if (!title) { tost('请输入任务标题'); return }
    var pjn = null
    // 优先从弹窗中的项目选择器读取（首页看板），回退到当前项目详情页
    var projSel = document.getElementById('ntProject')
    if (projSel && projSel.value) {
      pjn = pj(projSel.value)
    }
    if (!pjn) pjn = pj(sel[0])
    if (!pjn) { tost('项目不存在'); return }
    var goal = document.getElementById('ntGoal').value.trim(), acText = document.getElementById('ntAc').value.trim()
    var acLines = acText ? acText.split('\n').filter(function(x) { return x.trim() }).map(function(x) { return '- [ ] ' + x.trim() }).join('\n') : ''
    var prio = document.getElementById('ntPriority').value, due = document.getElementById('ntDue').value, today = todayLocal()
    var startVal = document.getElementById('ntStart') ? document.getElementById('ntStart').value : ''
    var status = document.getElementById('ntStatus') ? document.getElementById('ntStatus').value : 'open'
    var handler = document.getElementById('ntHandler') ? document.getElementById('ntHandler').value.trim() : ''
    // 重复周期设置（从全局配置读取，RepeatFields 同步写入）
    var repCfg = window.__pwRepeatConfig
    var repEnabled = !!(repCfg && repCfg.mode === 'fixed')
    var repUnit = repCfg ? repCfg.unit : ''
    var repEvery = repCfg ? (repCfg.every || '1') : ''
    var repDay = repCfg ? (repCfg.day || '') : ''
    var repAnchor = repCfg ? repCfg.anchor : (due || today)
    var repFm = repEnabled
      ? 'repeat_mode: fixed\nrepeat_unit: ' + repUnit + '\nrepeat_every: ' + repEvery + (repDay ? '\nrepeat_day: ' + repDay : '') + '\nrepeat_anchor: ' + repAnchor + '\n'
      : ''
    window.__pwRepeatConfig = null
    // 开始时间：用户填了才写 start（否则不写，保持待办 open）
    var startFm = startVal ? ('start: ' + startVal + '\n') : ''
    var content = '---\ntitle: ' + title + '\nstatus: ' + status + '\npriority: ' + prio + '\nhandler: ' + handler + '\nproject: ' + pjn.title + '\n' + startFm + (due ? 'due: ' + due + '\n' : '') + repFm + 'tags:\n  - task\n---\n\n# ' + title + '\n\n## 目标\n' + goal + '\n\n## 任务详情\n（任务背景、目的、方案等补充信息，可自由组织子标题）\n\n## 验收标准\n' + acLines + '\n\n## 推进记录\n- ' + today + ' 创建任务\n'
    var projDir = pjn.dir || pjn.title
    runSpec({ op: 'ensure_dir', path: PROOT + '/' + projDir + '/tasks' })
      .then(function() { return runSpec({ op: 'write', path: PROOT + '/' + projDir + '/tasks/任务-' + title + '.md', content: content }) })
      .then(function() { setMd(null); load(); tost('已创建任务「' + title + '」'); logOp(pjn ? (pjn.dir || pjn.title) : '', title, 'create_task', '「' + (pjn ? (pjn.title || pjn.dir) : '') + '」创建任务「' + title + '」') })
      .catch(function(e) { setErr(friendlyErr(e)); try { alert('创建任务失败：' + ((e && e.message) || String(e)).slice(0, 200)) } catch(_) {} })
    } catch (e) { console.error('[pw] doCreateTask throw:', e); try { alert('创建失败：' + ((e && e.message) || String(e)).slice(0, 120)) } catch(_) {} }
  }
  function doCreateCmd() {
    var name = document.getElementById('ncName').value.trim(); if (!name) { tost('请输入指令标题'); return }
    var content = document.getElementById('ncContent').value.trim()
    runSpec({ op: 'cmd_create', name: name, title: name, content: content || '' })
      .then(function(r) {
        if (r && r.ok) { setMd(null); tost('已创建指令「' + name + '」'); window.__pwNeedReloadCmds = true }
        else { tost('创建失败：' + ((r && r.error) || '')) }
      })
      .catch(function(e) { setErr(friendlyErr(e)) })
  }
  function createKanbanTask(t_) {
    // 状态切到 Agent → 自动创建 kanban task（幂等：kanban_task_id 为空才创建）
    var pjn = pj(t_.project)
    var ws = pjn ? VAULT + '/' + PROOT + '/' + (pjn.dir || pjn.title) : ''
    runSpec({
      op: 'kanban_create',
      title: t_.title,
      body: '## 目标\n' + (t_.goal || '') + '\n\n## 任务详情\n' + (t_.task_detail || '') + '\n\n## 验收标准\n' + ((t_.acceptance_criteria || []).map(function(x) { return '- [ ] ' + x }).join('\n')),
      assignee: 'business_analysis',
      workspace_path: ws,
      idempotency_key: 'pw:' + t_.path,
      board: 'default',
    }).then(function(res) {
      if (res && res.task_id) {
        runSpec({ op: 'set_property', path: t_.path, field: 'kanban_task_id', value: res.task_id }).catch(function(e) { console.error('[pw] kanban_task_id write failed:', e) })
        // 立即触发 dispatcher 消费 ready 任务
        runSpec({ op: 'kanban_dispatch', board: 'default', max: 1 }).catch(function(e) { console.error('[pw] kanban_dispatch failed:', e) })
      }
    }).catch(function(e) { console.error('[pw] kanban_create failed:', e) })
  }
  function doSetField(t_, field, value, skipSetDw) {
    // 乐观更新：创建新对象，不直接修改原引用（React immutability）
    var updated = Object.assign({}, t_)
    updated[field] = value
    if (field === 'status' && (value === 'Done' || value === 'Dropped')) {
      updated.complete = todayLocal()
    }
    if (!skipSetDw) setDw(updated)
    var newTs = ts[0].slice()
    for (var i = 0; i < newTs.length; i++) {
      if (newTs[i].path === t_.path) {
        newTs[i] = Object.assign({}, newTs[i])
        newTs[i][field] = value
        if (field === 'status' && (value === 'Done' || value === 'Dropped')) newTs[i].complete = todayLocal()
      }
    }
    setTs(newTs)
    var specs = [{ op: 'set_property', path: t_.path, field: field, value: value }]
    if (field === 'status' && (value === 'Done' || value === 'Dropped')) {
      specs.push({ op: 'set_property', path: t_.path, field: 'complete', value: todayLocal() })
    }
    if (field === 'status' && value === 'Agent') {
      if (t_.kanban_task_id) {
        // 已有 kanban task → 检查是否活跃，archive 则清掉重创
        runSpec({ op: 'kanban_status', task_id: t_.kanban_task_id, board: 'default' }).then(function(res) {
          if (res && res.status === 'archived') {
            runSpec({ op: 'set_property', path: t_.path, field: 'kanban_task_id', value: '' }).then(function() {
              // 用更新后的对象创建 kanban task，而非修改原引用
              var updatedForKanban = Object.assign({}, t_, { kanban_task_id: '' })
              createKanbanTask(updatedForKanban)
            }).catch(function(e) { console.error('[pw] kanban_task_id clear failed:', e) })
          }
        }).catch(function(e) { console.error('[pw] kanban_status check failed:', e) })
      } else {
        createKanbanTask(updated)
      }
    }
    // 重复任务：完成/放弃时自动创建下一个周期任务
    if (field === 'status' && (value === 'Done' || value === 'Dropped') && t_.repeat_mode) {
      runSpec({ op: 'repeat_next', path: t_.path }).then(function(rr) {
        if (rr && rr.ok) {
          tost('已生成下一周期任务：' + (rr.title || rr.due || ''))
          load()
        } else if (rr && rr.error === 'EXISTS') {
          // 已存在同日期任务，跳过
        } else {
          console.error('[pw] repeat_next:', rr)
        }
      }).catch(function(e) { console.error('[pw] repeat_next failed:', e) })
    }
    return Promise.all(specs.map(function(s) { return runSpec(s) }))
      .then(function() {
        tost('已更新')
        // 编辑后触发开始时间自动流转（改 start/status 后重新判断）
        autoStartFlow()
        if (field === 'status' && value !== t_[field]) logOp(t_.project || '', t_.title, 'status_change', '「' + (t_.project || '') + '」任务「' + t_.title + '」状态变更：' + (PST[t_[field]] || t_[field]) + ' → ' + (PST[value] || value))
      })
      .catch(function(e) {
        console.error('[pw] doSetField failed:', field, value, e)
        tost('失败：' + ((e && e.message) || '').slice(0, 40))
        // 回滚：恢复原始对象（frontmatter 已写入无法回滚，但 UI 状态至少恢复一致）
        setDw(t_)
        var rb = ts[0].slice()
        for (var i = 0; i < rb.length; i++) { if (rb[i].path === t_.path) rb[i] = t_ }
        setTs(rb)
      })
  }
  function doAddLog(t_) {
    var inp = document.getElementById('logInput'); if (!inp) return; var text = inp.value.trim(); if (!text) return
    var now = new Date()
    var p2 = function(n) { return (n < 10 ? '0' : '') + n }
    var logDate = p2(now.getMonth() + 1) + '-' + p2(now.getDate()) + ' ' + p2(now.getHours()) + ':' + p2(now.getMinutes()) + ':' + p2(now.getSeconds())
    var yamlEntry = '- date: ' + logDate + '\n'
      + '  type: manual\n'
      + '  summary: ' + text.replace(/\n/g, ' ') + '\n'
    // 乐观更新 UI：构造 YAML 条目对象
    var newLog = { type: 'yaml', date: now.getFullYear() + '-' + logDate, raw_date: logDate, summary: text, logType: 'manual', sessions: [], deliverables: [], decisions: [], risks: [], pending: [] }
    var updated = Object.assign({}, t_, { logs_yaml: (t_.logs_yaml || '') + (t_.logs_yaml ? '\n' : '') + yamlEntry.trimEnd() })
    setDw(updated)
    var newTs = ts[0].slice()
    for (var i = 0; i < newTs.length; i++) {
      if (newTs[i].path === t_.path) { newTs[i] = updated }
    }
    setTs(newTs)
    // 写入文件：add_log op（YAML 条目自动追加到围栏块，无需传整个文件）
    runSpec({ op: 'add_log', path: t_.path, text: yamlEntry.trimEnd() }).then(function() {
      tost('已添加推进记录')
    }).catch(function(e) { console.error('[pw] addLog failed:', e); setDw(t_); tost('写入失败') })
    inp.value = ''
  }
  function doSetProjField(pjn, field, value) {
    // 乐观更新 ps
    var newPs = ps[0].slice()
    for (var i = 0; i < newPs.length; i++) {
      if (newPs[i].path === pjn.path) {
        newPs[i] = Object.assign({}, newPs[i])
        newPs[i][field] = value
        if (field === 'status' && (value === 'Done' || value === 'Dropped')) newPs[i].complete = todayLocal()
      }
    }
    setPs(newPs)
    var specs = [{ op: 'set_property', path: pjn.path, field: field, value: value }]
    if (field === 'status' && (value === 'Done' || value === 'Dropped')) {
      specs.push({ op: 'set_property', path: pjn.path, field: 'complete', value: todayLocal() })
    }
    return Promise.all(specs.map(function(s) { return runSpec(s) }))
      .then(function() { tost('已更新'); if (field === 'status') logOp(pjn.title || pjn.dir, '', 'project_status', '项目「' + (pjn.title || pjn.dir) + '」状态变更：' + (PST[pjn.status] || pjn.status) + ' → ' + (PST[value] || value)) })
      .catch(function(e) { console.error('[pw] doSetProjField failed:', field, value, e); tost('失败：' + ((e && e.message) || '').slice(0, 40)); load() })
  }

  function doSaveOv() {
    var pjn = pj(sel[0]); if (!pjn) return; var text = document.getElementById('editInput').value.trim(), sec = ef[0] === 'bg' ? '项目背景' : '项目目标'
    var newPs = ps[0].slice()
    for (var i = 0; i < newPs.length; i++) {
      if (newPs[i].title === sel[0]) {
        newPs[i] = Object.assign({}, newPs[i])
        if (ef[0] === 'bg') newPs[i].background = text
        else newPs[i].goal = text
      }
    }
    setPs(newPs)
    updateSection(pjn.path, sec, text)
      .then(function() { setEf(null); tost('已保存') })
      .catch(function(e) { setErr(friendlyErr(e)) })
  }
  function loadSessions(projDir) {
    // cwd 为唯一信源（worker session 的 cwd 已由 kanban_link_session 补写）
    return sh('env HOME=/Users/ben python3 ' + SCRIPT + ' save_sessions "' + projDir + '" ""').then(function(o) {
      var info = JSON.parse(o); var total = info.len; var pid = info.pid || ''; var chunks = []
      for (var i = 0; i < total; i += 3900) chunks.push(i)
      return Promise.all(chunks.map(function(off) {
        return sh('env HOME=/Users/ben python3 ' + SCRIPT + ' read_sessions ' + off + ' 3900 ' + pid).then(function(c) { return c.trim() })
      })).then(function(parts) {
        var b64 = parts.join(''); var sessions = jp(b64).sessions || []
        // 同步：将 cwd 查到的 session_ids 写入项目 frontmatter（存档记录）
        var pjn = ps[0].filter(function(p) { return (p.dir || p.title) === projDir })[0]
        if (pjn && sessions.length) {
          var ids = sessions.map(function(s) { return s.id }).join(',')
          runSpec({ op: 'set_property', path: pjn.path, field: 'session_ids', value: ids }).catch(function(e) { console.error('[pw] session_ids sync failed:', e) })
        }
        return sessions
      })
    }).catch(function(e) { console.error('[pw] loadSessions failed:', e); return [] })
  }
  function doCreateSess(pjn, task) {
    var projDir = pjn.dir || pjn.title
    var cwd = VAULT + '/' + PROOT + '/' + projDir
    // Hermes desktop 的 session.create 优先使用 host.state.cwd，先设置确保正确
    try { host.state.cwd.set(cwd) } catch(e) { console.error('[pw] host.state.cwd.set failed:', e) }
    host.request('session.create', { cwd: cwd, source: 'desktop', cols: 96 }).then(function(r) {
      var sid = r && (r.stored_session_id || r.session_id)
      if (sid) {
        // 若从任务抽屉发起，将 session_id 记录到任务 frontmatter（存档记录，不做信源）
        if (task) {
          var tPrev = task.session_ids || ''
          var tList = tPrev ? tPrev.split(',').filter(Boolean) : []
          if (tList.indexOf(sid) < 0) { tList.push(sid) }
          runSpec({ op: 'set_property', path: task.path, field: 'session_ids', value: tList.join(',') }).catch(function(e) { console.error('[pw] session_ids write failed:', e) })
        }
        host.navigate('/' + encodeURIComponent(sid))
      }
      loadSessions(projDir).then(setSess)
      tost('已创建会话')
    }).catch(function(e) { tost('会话创建失败：' + ((e && e.message) || '未知错误')) })
  }
  function doHandleTask(t) {
    // 与 Inbox"去处理"一致：把任务文件带回 chat 输入框（作为 chip），不开新 session
    var projDir = t.dir || ''
    window.__pwPreloadCtx = { type: 'issue', name: t.title || '任务', dir: projDir, path: t.path, project: t.project, goal: t.goal, task_detail: t.task_detail, acceptance_criteria: t.acceptance_criteria }
    window.__pwGoChat = true
    setDw(null)
    host.navigate('/agent')
    tost('已带回 chat，可继续输入或发送')
  }
  // ─── 删除任务 ───────────────────────────────────────────
  function doDeleteTask(t) {
    if (!window.confirm('确定删除任务「' + (t.title || '') + '」？此操作不可恢复')) return
    runSpec({ op: 'delete_file', path: t.path }).then(function() {
      setDw(null)
      load()
      tost('已删除任务「' + (t.title || '') + '」')
      logOp(t.project || '', t.title, 'delete_task', '「' + (t.project || '') + '」删除任务「' + (t.title || '') + '」')
    }).catch(function(e) { tost('删除失败：' + ((e && e.message) || '').slice(0, 40)) })
  }
  // ─── 重命名任务标题 ─────────────────────────────────────
  function doRenameTitle(t, newTitle) {
    var nt = (newTitle || '').trim()
    if (!nt) { tost('标题不能为空'); return }
    if (nt === t.title) { setDw(Object.assign({}, t)); return }
    runSpec({ op: 'rename_title', path: t.path, new_title: nt }).then(function(r) {
      // 更新 UI 状态：title + path（若文件名变了）
      var updated = Object.assign({}, t, { title: nt })
      if (r && r.path) updated.path = r.path
      setDw(updated)
      var newTs = ts[0].slice()
      for (var i = 0; i < newTs.length; i++) {
        if (newTs[i].path === t.path) { newTs[i] = Object.assign({}, newTs[i], { title: nt }); if (r && r.path) newTs[i].path = r.path }
      }
      setTs(newTs)
      load()
      tost('已重命名为「' + nt + '」')
      logOp(t.project || '', t.title, 'rename_task', '「' + (t.project || '') + '」任务重命名：' + t.title + ' → ' + nt)
    }).catch(function(e) { tost('重命名失败：' + ((e && e.message) || '').slice(0, 40)) })
  }
  // ─── Review 操作 ─────────────────────────────────────────
  function doReviewResume(t) {
    // 人为介入处理：resume worker session，人工在对话中修正
    var ids = (t.session_ids || '').split(',').filter(Boolean)
    var sid = ids[ids.length - 1] || ''
    if (!sid) { tost('没有可恢复的会话'); return }
    host.request('session.resume', { session_id: sid }).then(function() {
      host.navigate('/' + encodeURIComponent(sid))
    }).catch(function(e) { tost('恢复失败：' + ((e && e.message) || '未知错误')) })
  }
  function doReviewPass(t) {
    // 确认通过 → 任务状态 Done + 回写 kanban complete
    var today = todayLocal()
    runSpec({ op: 'set_property', path: t.path, field: 'status', value: 'Done' })
      .then(function() { return runSpec({ op: 'set_property', path: t.path, field: 'complete', value: today }) })
      .then(function() {
        if (t.kanban_task_id) {
          runSpec({ op: 'kanban_complete', task_id: t.kanban_task_id, summary: '人工确认通过', board: 'default' }).catch(function(e) { console.error('[pw] kanban_complete failed:', e) })
        }
        ld().then(function(r) { setPs(r.projects || []); setTs(r.tasks || []) }).catch(function(e) { console.error('[pw] refresh after review failed:', e) })
        setDw(null)
        tost('已确认完成'); logOp(t.project || '', t.title, 'status_change', '「' + (t.project || '') + '」任务「' + t.title + '」状态变更：待人为确认 → 已完成')
      }).catch(function(e) { tost('失败：' + ((e && e.message) || '').slice(0, 40)) })
  }

  // 计算所有处理人列表（用于 HandlerPicker），过滤掉 @周本
  var allHandlers = []
  var seenH = {}
  ts[0].forEach(function(t) { if (t.handler && t.handler !== '@周本' && !seenH[t.handler]) { seenH[t.handler] = 1; allHandlers.push(t.handler) } })

  return {
    ps: ps[0], ts: ts[0], loading: loading[0], err: err[0],
    sel: sel[0], vw: vw[0], dw: dw[0], tb: tb[0], md: md[0], ef: ef[0], sess: sess[0], to: to[0], sessCounts: sessCounts,
    handlers: allHandlers,
    setSel: setSel, setVw: setVw, setDw: setDw, setTb: setTb, setMd: setMd, setEf: setEf, setSess: setSess,
    load: load, pts: pts, pj: pj, tost: tost,
    updateSection: updateSection, toggleAc: toggleAc,
    doCreateProj: doCreateProj, doCreateTask: doCreateTask, doCreateCmd: doCreateCmd, doSetField: doSetField,
    doAddLog: doAddLog, doSaveOv: doSaveOv, doSetProjField: doSetProjField, loadSessions: loadSessions, doCreateSess: doCreateSess,
    doHandleTask: doHandleTask,
    doDeleteTask: doDeleteTask, doRenameTitle: doRenameTitle,
    doReviewResume: doReviewResume, doReviewPass: doReviewPass,
  }
}

// ═══ 原语组件工厂 ═════════════════════════════════════════
// 原则：视图只准引用原语；原语内部只引用 token。改控件形态只改这里。
// 控件尺寸 token（原语层引入）
var T = { btnH: '24px', btnHlg: '32px', r8: '8px', r5: '5px', r10: '10px' }

// 主按钮（深灰实底，Beautiful UI 约定）。variant: 'lg'(32px高) | 'modal'(模态确认,r10,自适应高)
function Btn(props) {
  var isModal = props.variant === 'modal'
  var h = props.variant === 'lg' ? T.btnHlg : T.btnH
  var pad = isModal ? 'px-3 py-1' : 'px-2.5'
  return jsx('span', {
    className: 'inline-flex items-center' + (props.gap ? ' gap-1' : '') + ' text-[0.6875rem] font-medium ' + pad + ' cursor-pointer select-none transition-all hover:opacity-85',
    style: isModal
      ? { background: BTN, color: '#fff', borderRadius: T.r10, boxShadow: SH_SOFT }
      : { background: BTN, color: '#fff', borderRadius: T.r8, boxShadow: SH_SOFT, height: h, lineHeight: h },
    onClick: props.onClick, children: props.children,
  })
}

// 文本输入/下拉/多行（focus 灰边约定）。as: 'input'(默认)|'select'|'textarea'
function Input(props) {
  var tag = props.as || 'input'
  var base = { color: INK, borderColor: props.border || IN_BRD }
  if (tag === 'textarea') {
    Object.assign(base, { borderRadius: T.r8, minHeight: props.minHeight || '88px', lineHeight: '1.7' })
  } else {
    Object.assign(base, { borderRadius: props.radius || T.r5, height: props.height || T.btnHlg, lineHeight: props.height || T.btnHlg })
  }
  var common = {
    className: 'bg-white px-2.5 text-[0.75rem] border outline-none' + (tag === 'select' ? ' cursor-pointer' : '') + (tag === 'textarea' ? ' transition-all resize-y w-full py-2' : '') + (props.classNameExtra || ''),
    style: base,
    id: props.id, defaultValue: props.defaultValue, type: tag === 'input' ? (props.type || 'text') : undefined,
    autoFocus: props.autoFocus, placeholder: props.placeholder,
    onFocus: function(e) { e.target.style.borderColor = FOCUS_BRD },
    onBlur: function(e) { e.target.style.borderColor = props.border || IN_BRD },
    onKeyDown: props.onKeyDown, onChange: props.onChange,
  }
  if (tag === 'select') return jsx('select', Object.assign({}, common, { children: props.options.map(function(o) { return jsx('option', { value: o[0], children: o[1] }, o[0]) }) }))
  return jsx(tag, common)
}

// ═══ 样式系统（全新）══════════════════════════════════════
// 原则：无可见边框的页面层级、大圆角、软阴影、着色徽章、充足留白
var S = {
  // 页面
  page: 'h-full overflow-y-auto',
  wrap: 'max-w-[1040px] mx-auto px-8 py-8',

  // 文字
  h1: 'text-[1.25rem] font-semibold tracking-[-0.01em]',
  h2: 'text-[0.9375rem] font-semibold',
  body: 'text-[0.8125rem] leading-[1.7]',
  mut: 'text-[0.75rem]',
  cap: 'text-[0.6875rem] font-medium tracking-[0.02em]',

  // 按钮（Beautiful UI: 1px 边框 + 极浅阴影，白字/主色按钮）
  btnPrm: 'inline-flex items-center gap-1.5 text-[0.8125rem] font-medium px-4 py-2 rounded-lg text-white cursor-pointer select-none transition-all duration-150 hover:opacity-90',
  btnSec: 'inline-flex items-center gap-1.5 text-[0.8125rem] font-medium px-3.5 py-2 rounded-lg cursor-pointer select-none transition-all duration-150 hover:bg-[#f7f8f9]',
  btnTxt: 'inline-flex items-center text-[0.8125rem] px-3 py-2 rounded-lg cursor-pointer select-none transition-colors hover:bg-[#f7f8f9]',
  iconBtn: 'flex items-center justify-center w-8 h-8 rounded-lg cursor-pointer transition-colors hover:bg-[#f7f8f9]',

  // 徽章（软底着色 pill）
  pill: 'inline-flex items-center text-[0.6875rem] font-medium px-2 py-[3px] rounded-full leading-none',

  // 表单
  input: 'w-full bg-white rounded-lg px-3.5 py-3 text-[0.8125rem] border border-[#e0e2e5] text-[#1f2124] placeholder:text-[#b8bbc1] outline-none transition-all focus:border-[#0285ff] focus:shadow-[0_0_0_3px_rgba(2,133,255,0.12)]',
  fLabel: 'block mb-2 text-[0.75rem]',
  hint: 'text-[0.6875rem] mt-2 leading-relaxed',

  // 卡片 / 看板
  card: 'rounded-xl bg-white transition-all',
  column: 'rounded-xl p-2.5 flex flex-col',
  taskCard: 'rounded-lg bg-white px-3.5 py-3 cursor-pointer transition-all mb-2',
}

// ─── 空状态 / 加载 ───────────────────────────────────────
function Center(props) {
  return jsxs('div', { className: 'flex flex-col items-center justify-center gap-3 py-24', children: [
    jsx('span', { style: { color: FAINT }, children: jsx(Codicon, { name: props.icon, className: 'text-xl' + (props.spin ? ' animate-spin' : '') }) }),
    jsx('span', { className: 'text-[0.8125rem]', style: { color: MUT }, children: props.text }),
  ]})
}

// ─── Chat Home（chat-first 首页） ──────────────────────────────
// 输入区采用「原生 contenteditable」：React 只渲染空容器，编辑器本体由
// useEffect 原生创建并 append，React 重渲染不会触碰（文本永不丢失）；
// chips 原生插入光标位置，实现真正的 @ 位置行内嵌入。
// 草稿持久化：切 tab 会卸载 ChatHome（state 销毁），用模块级草稿保存
// 输入框完整 DOM（html，保序还原文本与 chip 的混排）+ chips 数据（state 用），
// 挂载时恢复——切换 tab 回来内容不丢失、顺序还原。
var __chatDraft = { html: '', ctx: [] }

function ChatHome(R) {
  // ── state ──
  var ctx = useState(__chatDraft.ctx.slice()), ctxSel = ctx[0], setCtxSel = ctx[1]        // [{type:'project'|'issue', name, path}]
  var atv = useState(false), atOpen = atv[0], setAtOpen = atv[1]      // @ 选择面板
  var cmdv = useState([]), cmds = cmdv[0], setCmds = cmdv[1]          // 指令列表
  var ctv = useState(false), cmdPanel = ctv[0], setCmdPanel = ctv[1]  // 指令面板
  var slv = useState(false), slashOpen = slv[0], setSlashOpen = slv[1] // / skills 面板
  var skv = useState([]), skills = skv[0], setSkills = skv[1]          // skills 列表（catalog）
  var slq = useState(''), slashQuery = slq[0], setSlashQuery = slq[1] // / 面板搜索
  var six = useState(0), slashIdx = six[0], setSlashIdx = six[1]      // / 面板键盘选中
  var composingRef = useRef(false)                                     // IME 组合中标记（Enter 发送保护）
  var inv = useState([]), inboxItems = inv[0], setInboxItems = inv[1]  // inbox 列表（@ 面板使用）
  var rsv = useState([]), recentSess = rsv[0], setRecentSess = rsv[1] // 最近会话
  var ttv = useState(''), typed = ttv[0], setTyped = ttv[1]           // 输入文本（供发送）
  var atq = useState(''), atQuery = atq[0], setAtQuery = atq[1]       // @ 面板搜索
  var aix = useState(0), atIdx = aix[0], setAtIdx = aix[1]            // @ 面板键盘选中索引
  var snd = useState(false), sending = snd[0], setSending = snd[1]    // 发送中
  var pls = useState(false), plusOpen = pls[0], setPlusOpen = pls[1]   // + 菜单
  var psub = useState(null), plusSub = psub[0], setPlusSub = psub[1]   // + 菜单二级（'projects'）
  var mh = useState(false), mascotHover = mh[0], setMascotHover = mh[1] // 吉祥物 hover（弹出猫头）
  var plusRef = useRef(null)                                          // + 菜单容器（点击外部关闭）
  var mascotRef = useRef(null)                                        // 吉祥物容器（测量定位）
  var chatCardRef = useRef(null)                                      // 主对话卡（测量上沿）
  var wrapRef = useRef(null)                                          // React 容器 div
  var edRef = useRef(null)                                            // 原生 contenteditable
  // 最新状态 refs（keydown 监听器闭包固化，需读 ref 拿最新值）
  var stRef = useRef({ atOpen: false, atIdx: 0, atList: [], ctxSel: [], cmds: [], slashOpen: false, slashIdx: 0, slashList: [] })
  stRef.current.atOpen = atOpen; stRef.current.atIdx = atIdx; stRef.current.ctxSel = ctxSel; stRef.current.cmds = cmds
  stRef.current.slashOpen = slashOpen; stRef.current.slashIdx = slashIdx; stRef.current.slashList = filteredSkills
  // 同步草稿（切 tab 卸载时保留输入）：html 保序 + ctx 供 state 恢复
  try { if (edRef.current) __chatDraft.html = edRef.current.innerHTML } catch(e) {}
  __chatDraft.ctx = ctxSel
  var inputRef = useRef(null)                                         // textarea ref
  var atPanelRef = useRef(null)                                       // @ 面板容器（外部点击关闭用）
  var cmdPanelRef = useRef(null)                                      // 指令面板容器

  // ── 数据加载 ──
  function loadRecents() {
    // 大输出统一走 run 模式分片机制（Python 端 hpw_data_*.b64），无需前端 gzip 解压
    runSpec({ op: 'recent_sessions', limit: 20 }).then(function(r) {
      setRecentSess((r && r.sessions) || [])
    }).catch(function(e) { console.error('[pw] recent_sessions failed:', e) })
  }
  function loadCmds() {
    runSpec({ op: 'cmd_list' }).then(function(r) { setCmds(r.cmds || []) })
      .catch(function(e) { console.error('[pw] cmd_list failed:', e) })
  }
  useEffect(function() { loadRecents(); loadCmds(); loadSkills(); loadInboxItems() }, [])
  function loadInboxItems() {
    runSpec({ op: 'inbox_list' }).then(function(r) { setInboxItems(r.items || []) }).catch(function(e) { console.error('[pw] inbox_list failed:', e) })
  }
  // 吉祥物定位：测量主对话卡上沿相对 720px 容器的偏移，猫 top 设为卡上沿 - 耳朵露出量（耳朵尖贴红线）
  useEffect(function() {
    try {
      if (mascotRef.current && chatCardRef.current) {
        var card = chatCardRef.current.getBoundingClientRect()
        var box = mascotRef.current.offsetParent ? mascotRef.current.offsetParent.getBoundingClientRect() : null
        var relTop = box ? (card.top - box.top) : card.top
        // 吉祥物容器顶部 = 卡上沿 - 露出高度（初始露 11.5px；hover 再上移 7.8px → 露出 55%）
        mascotRef.current.style.top = String(relTop - 11.5) + 'px'
      }
    } catch(e) { console.error('[pw] mascot position:', e) }
  })
  // + 菜单：点击外部空白处关闭
  useEffect(function() {
    function onDocMouseDown(e) {
      if (!e.target || !e.target.closest) return
      // 点击 + 菜单内部（一级或二级）不关闭
      if (e.target.closest('[data-plus-menu]')) return
      setPlusOpen(false); setPlusSub(null)
    }
    document.addEventListener('mousedown', onDocMouseDown)
    return function() { document.removeEventListener('mousedown', onDocMouseDown) }
  }, [])
  // 冷启动兜底：Projects/Issues 数据为空时主动重新拉取（重启后 gateway 时序可能导致 R.load 失败/未触发）。
  // 最多重试 3 次（用模块级计数），避免 R.load 持续失败导致无限循环
  if (window.__pwBootRetry === undefined) window.__pwBootRetry = 0
  useEffect(function() {
    if ((!R.ps || R.ps.length === 0) && (!R.ts || R.ts.length === 0) && !R.loading && window.__pwBootRetry < 3) {
      window.__pwBootRetry++
      try { R.load() } catch(e) { console.error('[pw] reload after boot failed:', e) }
    }
  }, [R.ps, R.ts, R.loading])

  // ── 原生编辑器管理（React 不管理 contenteditable 内部） ──
  // 挂载：创建原生 contenteditable 挂到容器
  useEffect(function() {
    if (!wrapRef.current || edRef.current) return
    var ed = document.createElement('div')
    ed.contentEditable = 'true'
    ed.setAttribute('data-chat-editor', '1')
    ed.style.cssText = "font-size:14px;color:#1f2124;line-height:1.6;min-height:101px;background:transparent;outline:none;white-space:pre-wrap;word-break:break-word;cursor:text;"
    ed.addEventListener('input', function() {
      // 同步 typed（供发送），检测 @ / !
      var t = ''
      try { t = getEditorText(ed) } catch(err) { console.error('[pw] getEditorText err:', err) }
      setTyped(t)
      // 直接同步草稿：完整 DOM（保序还原文本与 chip 混排）
      try { __chatDraft.html = ed.innerHTML } catch(e) {}
      // 更新 placeholder（真空显示，删空后也恢复提示）
      try { if (window.__chatUpdatePh) window.__chatUpdatePh() } catch(e) {}
      // @ 检索：@ 后的文字作为筛选词，面板实时过滤（无需移动鼠标进搜索框）
      var ai = String(t).lastIndexOf('@')
      if (ai >= 0) { openAt(); setAtQuery(String(t).slice(ai + 1)) }
      else if (stRef.current.atOpen) { setAtOpen(false); setAtQuery('') }
      // / 检索：文本含 / 即触发（参考 @ 行为——输入框已有内容也能唤起），/ 后无空格才视为命令词
      // （选中插入的是 "/cmd " 带空格，继续输入含空格不会再次触发；首次输入 "/grill" 无空格正常触发）
      var sli = String(t).lastIndexOf('/')
      var afterSlash = sli >= 0 ? String(t).slice(sli + 1) : ''
      var slashIsCmd = sli >= 0 && afterSlash.indexOf(' ') < 0
      if (!stRef.current.atOpen && !stRef.current.cmdPanel && slashIsCmd) { openSlash(); setSlashQuery(afterSlash) }
      else if (stRef.current.slashOpen && !slashIsCmd) { setSlashOpen(false); setSlashQuery('') }
      // 快捷指令：任何时候输入 ! 都触发（输入框有内容也能），@ 面板打开时不抢；无指令也弹面板显示"暂无指令"
      if (!stRef.current.atOpen && !stRef.current.slashOpen && String(t).indexOf('!') >= 0) openCmds()
      // 指令面板打开时输入了其他内容（非纯 ! 文本）→ 关面板
      else if (stRef.current.cmdPanel && String(t).indexOf('!') < 0) setCmdPanel(false)
    })
    ed.addEventListener('keydown', function(e) {
      // @ 面板打开时：上下键/回车/Esc 由 atKeyNav 处理（读 stRef 最新状态）
      if (stRef.current.atOpen && (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === 'Escape')) {
        if (atKeyNav(e)) { e.preventDefault(); return }
      }
      // / 面板打开时：上下键/回车/Esc 由 slashKeyNav 处理
      if (stRef.current.slashOpen && (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === 'Escape')) {
        if (slashKeyNav(e)) { e.preventDefault(); return }
      }
      // Enter 发送（不带动修饰键）；Shift+Enter 换行（contenteditable 默认插入 <br>）；Cmd/Ctrl+Enter 不处理
      // IME 保护：中文/日文/韩文输入法下 Enter 是确认候选词，不发送
      // （composingRef + isComposing 覆盖组合中；keyCode 229 覆盖 macOS 中文输入法 commit 后残留）
      if (e.key === 'Enter' && !e.shiftKey && !e.metaKey && !e.ctrlKey && !composingRef.current && !e.isComposing && e.keyCode !== 229) {
        e.preventDefault(); doSend(); return
      }
      // Backspace：文字删光且剩 chip 时受控删除 chip（用纯文本判断——getEditorText 含 chip 名会导致漏判，
      // 走浏览器默认删除 contentEditable=false 元素会破坏 DOM 结构）
      if (e.key === 'Backspace' && getEditorPlainText(ed).trim() === '' && stRef.current.ctxSel.length > 0) {
        e.preventDefault()
        rmCtx(stRef.current.ctxSel.length - 1)
      }
    })
    ed.addEventListener('compositionstart', function() { composingRef.current = true })
    ed.addEventListener('compositionend', function() { composingRef.current = false })
    ed.addEventListener('paste', function(e) {
      var cd = e.clipboardData || window.clipboardData
      var hasFiles = cd && cd.files && cd.files.length > 0
      if (hasFiles) {
        // 粘贴图片/文件 → 作为 file chip 加入上下文
        e.preventDefault()
        var files = Array.prototype.slice.call(cd.files)
        files.forEach(function(f) {
          if (!f) return
          var nm = f.name || '粘贴文件'
          // 图片：优先持久化到 composer 缓存（剪贴板截图是短生命周期临时路径，直接 attach 会失效），拿稳定路径
          if (f.type && f.type.indexOf('image/') === 0) {
            f.arrayBuffer().then(function(buf) {
              var ext = (f.name.match(/\.(\w+)$/) || [])[1] || 'png'
              if (window.hermesDesktop && window.hermesDesktop.saveImageBuffer) {
                return window.hermesDesktop.saveImageBuffer(buf, ext)
              }
              return ''
            }).then(function(saved) {
              var p = saved || ''
              if (!p) {
                try { if (window.hermesDesktop && window.hermesDesktop.getPathForFile) p = window.hermesDesktop.getPathForFile(f) } catch(e2) {}
              }
              if (!p && f.path) p = f.path
              if (!p) p = nm
              addCtxFrom({ type: 'file', name: nm, dir: '', path: p }, stRef.current.ctxSel || [])
            }).catch(function(e3) { console.error('[pw] paste image save failed:', e3) })
            return
          }
          // 非图片文件：直接取路径（getPathForFile）
          var p = ''
          try { if (window.hermesDesktop && window.hermesDesktop.getPathForFile) p = window.hermesDesktop.getPathForFile(f) } catch(e2) {}
          if (!p && f.path) p = f.path
          if (!p) p = nm
          addCtxFrom({ type: 'file', name: nm, dir: '', path: p }, stRef.current.ctxSel || [])
        })
        return
      }
      e.preventDefault()
      var t = (cd || {}).getData ? cd.getData('text/plain') : ''
      document.execCommand('insertText', false, t)
    })
    ed.addEventListener('click', function() { ed.focus() })
    wrapRef.current.appendChild(ed)
    edRef.current = ed
    // placeholder：JS 控制（:empty 不可靠——删空后 DOM 残留 <br> 导致不匹配）
    ed.setAttribute('data-placeholder', '向 Agent 下达任务，或 @ 项目 / Issue 作为上下文…')
    var style = document.createElement('style')
    style.id = 'chatEdStyle'
    style.textContent = "[data-chat-editor].is-empty:before{content:attr(data-placeholder);color:" + FAINT + ";pointer-events:none;}[data-chat-sending]{opacity:0.5;pointer-events:none;}.rs-scroll::-webkit-scrollbar{display:none}.rs-scroll:hover::-webkit-scrollbar{display:block;width:6px}.rs-scroll:hover::-webkit-scrollbar-thumb{background:#c6c6cd;border-radius:3px}.rs-scroll:hover::-webkit-scrollbar-track{background:transparent}@keyframes pwDrawerIn{from{transform:translateX(100%)}to{transform:translateX(0)}}@keyframes pwFadeIn{from{opacity:0}to{opacity:1}}@keyframes pwDrawerOut{from{transform:translateX(0)}to{transform:translateX(100%)}}@keyframes pwFadeOut{from{opacity:1}to{opacity:0}}[data-pw]{-webkit-user-select:text;user-select:text}[data-pw] *{-webkit-user-select:text;user-select:text}"
    document.head.appendChild(style)
    // 判断是否真空（无文本无 chip），切换 is-empty class
    window.__chatUpdatePh = function() {
      var e2 = edRef.current
      // ed 脱离文档时直接返回（发送后跳转、组件卸载时 stop 会调用——此时操作 detached ed 会触发 addRange 警告）
      if (!e2 || !document.contains(e2)) return
      var hasTxt = (getEditorPlainText(e2) || '').replace(/\s/g, '').length > 0
      var hasChip = e2.querySelectorAll('[data-chip-idx]').length > 0
      if (hasTxt || hasChip) {
        e2.classList.remove('is-empty')
      } else {
        // 真空：清掉 DOM 残留（<br>/空节点），避免光标停在 placeholder 末尾
        while (e2.firstChild) e2.removeChild(e2.firstChild)
        e2.classList.add('is-empty')
        // 光标移到元素最前
        try {
          var r = document.createRange()
          r.setStart(e2, 0); r.collapse(true)
          var s = window.getSelection()
          s.removeAllRanges(); s.addRange(r)
        } catch(e) {}
      }
    }
    window.__chatUpdatePh()
    // 恢复草稿：切 tab 回来时完整还原（文本 + chip 混排顺序不变）
    try {
      if (__chatDraft.html) {
        ed.innerHTML = __chatDraft.html
        setTyped(getEditorText(ed))
      }
      // 光标移到末尾（方便继续输入）
      caretToEnd(ed)
      try { if (window.__chatUpdatePh) window.__chatUpdatePh() } catch(e) {}
    } catch(e) { console.error('[pw] draft restore err:', e) }
    // 预载上下文：从 Inbox 详情"去处理"带回 chat 时，@ 该文件（append chip）
    try {
      if (window.__pwPreloadCtx) {
        var pc = window.__pwPreloadCtx
        window.__pwPreloadCtx = null
        var ns2 = (stRef.current.ctxSel || []).concat([pc])
        setCtxSel(ns2)
        __chatDraft.ctx = ns2
        ed.appendChild(chipNode(pc, ns2.length - 1))
        caretToEnd(ed)
        setTyped(getEditorText(ed))
        try { __chatDraft.html = ed.innerHTML } catch(e2) {}
        try { if (window.__chatUpdatePh) window.__chatUpdatePh() } catch(e2) {}
        ed.focus()
      }
    } catch(e) { console.error('[pw] preload ctx err:', e) }
    ed.focus()
  }, [])
  // sending 状态：输入框变灰 + 禁输入（过渡效果）
  // 冻结内容：不清空、光标隐藏（blur）、内容保持固定
  useEffect(function() {
    var ed = edRef.current
    if (ed) {
      if (sending) {
        ed.setAttribute('data-chat-sending', '1')
        ed.style.opacity = '0.5'
        ed.style.pointerEvents = 'none'
        // 隐藏光标：失焦（内容保留，但无闪烁光标），loading 结束后恢复焦点
        if (document.activeElement === ed) { try { ed.blur() } catch(e) {} }
      }
      else {
        ed.removeAttribute('data-chat-sending')
        ed.style.opacity = ''
        ed.style.pointerEvents = ''
      }
    }
  }, [sending])

  // 预载上下文消费：任务/Inbox"去处理"带回 chat 时 @ 该文件（append chip）
  // 独立 useEffect（每次渲染检查，不只在挂载）——分页容器内 ChatHome 已挂载时也能消费
  useEffect(function() {
    if (!window.__pwPreloadCtx) return
    var ed = edRef.current
    if (!ed || !document.contains(ed)) return
    var pc = window.__pwPreloadCtx
    window.__pwPreloadCtx = null
    var ns2 = (stRef.current.ctxSel || []).concat([pc])
    setCtxSel(ns2)
    __chatDraft.ctx = ns2
    ed.appendChild(chipNode(pc, ns2.length - 1))
    caretToEnd(ed)
    setTyped(getEditorText(ed))
    try { __chatDraft.html = ed.innerHTML } catch(e2) {}
    try { if (window.__chatUpdatePh) window.__chatUpdatePh() } catch(e2) {}
    ed.focus()
  })

  // 读取编辑器纯文本：文本节点原样，chip 输出其名称（保证 prompt 连贯）
  function getEditorText(ed) {
    if (!ed) return ''
    var out = ''
    ed.childNodes.forEach(function(n) {
      if (n.nodeType === 3) out += n.nodeValue  // 文本节点
      else if (n.getAttribute && n.getAttribute('data-chip-idx') != null) {
        // chip：输出名称（第一个子 span 的文本）
        var nm = n.firstChild ? (n.firstChild.textContent || '') : ''
        out += nm
      }
      else out += n.textContent
    })
    return out
  }

  // 读取纯文本（跳过 chips，不含 chip 名）——草稿持久化用，避免恢复时文本+chip 双重复
  function getEditorPlainText(ed) {
    if (!ed) return ''
    var out = ''
    ed.childNodes.forEach(function(n) {
      if (n.nodeType === 3) out += n.nodeValue
      else if (!(n.getAttribute && n.getAttribute('data-chip-idx') != null)) out += n.textContent
    })
    return out
  }

  // 创建 chip 节点（DOM 上存完整 item 数据，doSend 可直接从 DOM 读，不依赖 state）
  function chipNode(c, i) {
    var chip = document.createElement('span')
    chip.contentEditable = 'false'
    chip.setAttribute('data-chip-idx', String(i))
    chip.setAttribute('data-chip-type', c.type || '')
    chip.setAttribute('data-chip-dir', c.dir || '')
    chip.setAttribute('data-chip-path', c.path || '')
    chip.setAttribute('data-chip-name', c.name || '')
    chip.style.cssText = "display:inline-flex;align-items:center;gap:6px;height:24px;padding:0 8px 0 10px;border-radius:99px;font-size:12px;font-weight:500;vertical-align:middle;margin-right:6px;user-select:none;" + (c.type === 'project' ? 'background:' + PURPLE_T + ';color:' + PURPLE + ';' : c.type === 'file' ? 'background:#eef7ef;color:#2f9e44;' : c.type === 'inbox' ? 'background:' + ORANGE_T + ';color:#c97f10;' : 'background:' + ACCS + ';color:' + ACCD + ';')
    var txt = document.createElement('span'); txt.textContent = c.name
    var x = document.createElement('span'); x.textContent = '✕'
    x.style.cssText = 'cursor:pointer;opacity:0.6;font-size:11px;margin-left:6px;'
    x.onclick = function(e) { e.stopPropagation(); rmCtx(parseInt(chip.getAttribute('data-chip-idx'), 10)) }
    chip.appendChild(txt); chip.appendChild(x)
    return chip
  }

  // 从 DOM 读取所有 chips 的上下文（doSend 用它，不依赖 ctxSel state）
  function ctxFromDom(ed) {
    var out = []
    if (ed) {
      ed.querySelectorAll('[data-chip-idx]').forEach(function(n) {
        out.push({
          type: n.getAttribute('data-chip-type') || '',
          name: n.getAttribute('data-chip-name') || '',
          dir: n.getAttribute('data-chip-dir') || '',
          path: n.getAttribute('data-chip-path') || ''
        })
      })
    }
    return out
  }

  // 重建所有 chips（顺序渲染到编辑器开头）
  function renderChips() {
    var ed = edRef.current
    if (!ed) return
    ed.querySelectorAll('[data-chip-idx]').forEach(function(n) { n.remove() })
    ctxSel.forEach(function(c, i) {
      ed.insertBefore(chipNode(c, i), ed.firstChild)
    })
  }

  // 光标移到编辑器末尾
  function caretToEnd(ed) {
    if (!ed || !document.contains(ed)) return  // detached 时跳过（避免 addRange 警告）
    var r = document.createRange(); r.selectNodeContents(ed); r.collapse(false)
    var s = window.getSelection(); s.removeAllRanges(); s.addRange(r)
  }

  // ── 发送：创建 session + 关联 + 首条消息 ──
  function doSend() {
    var rawText = getEditorText(edRef.current).trim()
    if (!rawText || sending) return
    var proj = ctxSel.filter(function(x) { return x.type === 'project' })[0]
    var issue = ctxSel.filter(function(x) { return x.type === 'issue' })[0]
    // cwd 以任务所属项目为准（attach 的任务文件必须在 cwd 内才能被 file.attach 直接使用）；
    // 无任务时才用 @ 项目的目录。
    var projDir = issue ? issue.dir : (proj ? proj.dir : '')
    var cwd = projDir ? (VAULT + '/' + PROOT + '/' + projDir) : ''
    // 若 @ 了任务：attach 任务文件（相对 cwd 的路径，cwd=任务所属项目，保证文件存在）
    var attachPath = ''
    if (issue) {
      var m2 = String(issue.path || '').match(/tasks\/[^/]+\.md$/)
      attachPath = m2 ? m2[0] : ''
    }
    // 以 DOM 为准：若 ctxSel state 与 DOM chip 不一致，用 DOM 数据重建
    var domCtx = ctxFromDom(edRef.current)
    if (domCtx.length && (!ctxSel.length || domCtx.length !== ctxSel.length)) {
      ctxSel = domCtx
      proj = domCtx.filter(function(x) { return x.type === 'project' })[0]
      issue = domCtx.filter(function(x) { return x.type === 'issue' })[0]
      projDir = issue ? issue.dir : (proj ? proj.dir : '')
      cwd = projDir ? (VAULT + '/' + PROOT + '/' + projDir) : ''
      if (issue) {
        var m3 = String(issue.path || '').match(/tasks\/[^/]+\.md$/)
        attachPath = m3 ? m3[0] : ''
      }
    }
    setSending(true)
    // create 直接传 cwd 参数（13:32 验证成功的方式：不加 host.state.cwd.set，避免干扰）
    setTimeout(function() {
    host.request('session.create', { cwd: cwd || undefined, source: 'desktop', cols: 96 }).then(function(r) {
      var storedId = r && (r.stored_session_id || r.session_id)
      var runtimeId = r && r.session_id
      if (!storedId) { setSending(false); R.tost('创建会话失败'); return }
      // 确定性修复：create 的 cwd 参数在 desktop 可能不稳定（有时被忽略）。
      // 用 session.cwd.set 显式设置项目目录，确保 DB 落库 + 后续 @file 解析都正确。
      var cwdSetP = Promise.resolve()
      if (cwd) {
        cwdSetP = host.request('session.cwd.set', { session_id: runtimeId || storedId, cwd: cwd })
          .catch(function(e) { console.error('[pw] session.cwd.set failed:', e) })
      }
      cwdSetP.then(function() {
      // 若 @ 了任务：file.attach 附加任务文件，拿 @file: 引用（background 上下文）
      // path 用 issue.path 的完整绝对路径（VAULT + '/' + issue.path），比 cwd+attachPath 拼接更可靠
      // 支持多个：任务文件 + 上传的文件（type:'file' chip，path 为绝对路径）
      var attachTargets = []
      if (issue && issue.path) attachTargets.push(VAULT + '/' + issue.path)
      ;(ctxSel || []).forEach(function(c) {
        if (c.type === 'file' && c.path) attachTargets.push(c.path)
        // inbox chip 的 path 是 vault 相对路径（2. Project/Inbox/...），转绝对路径
        else if (c.type === 'inbox' && c.path) attachTargets.push(VAULT + '/' + c.path)
      })
      var attachPromise = Promise.resolve({ ref_text: '' })
      if (attachTargets.length) {
        // 逐个 file.attach，合并所有 @file: 引用
        var ap = Promise.resolve({ ref_text: '' })
        attachTargets.forEach(function(p) {
          ap = ap.then(function(acc) {
            return host.request('file.attach', { session_id: runtimeId || storedId, path: p })
              .then(function(a) {
                var prev = acc.ref_text || ''
                var add = (a && a.ref_text) || ''
                return { ref_text: prev ? (prev + '\n' + add) : add }
              })
              .catch(function(e) { console.error('[pw] file.attach failed:', p, e); return acc })
          })
        })
        attachPromise = ap
      }
      attachPromise.then(function(att) {
        var refText = (att && att.ref_text) || ''
        var promptText = refText ? (refText + '\n\n' + rawText) : rawText
        if (issue) {
          runSpec({ op: 'read', path: issue.path }).then(function(o) {
            var m = (o.content || '').match(/^session_ids:\s*(.*)$/m)
            var tList = m ? m[1].trim().split(',').filter(Boolean) : []
            if (tList.indexOf(storedId) < 0) tList.push(storedId)
            return runSpec({ op: 'set_property', path: issue.path, field: 'session_ids', value: tList.join(',') })
          }).catch(function(e) { console.error('[pw] session_ids write failed:', e) })
        }
        // 注意：不在 create 成功后清空编辑器——loading 期间内容保持冻结（用户要求）
        // 清空延迟到 finish()（loading 结束、跳转完成后）再执行，见 stop()
        // prompt.submit 用 runtime id。等待 lazy session 的 agent 构建完成。
        // loading 持续到前端真正进入新 session：
        // 订阅 host.state.focusedStoredSessionId，当它变成新 session 的 storedId
        // 说明前端焦点已切换到该 session（导航渲染完成），此时结束 loading。
        function finish() {
          function doNav() {
            try { if (typeof host.openSession === 'function') host.openSession(storedId) } catch(e) {}
          }
          var focused = host.state && host.state.focusedStoredSessionId
          var done = false
          function stop() {
            if (done) return
            done = true
            if (unsub) { try { unsub() } catch(e) {} }
            // loading 结束：此时已跳转到新 session，清空输入框 + chips 作为收尾
            // 跳转后 ChatHome 可能已卸载、ed detached——detached 时跳过 DOM 操作（避免 addRange 警告）
            try {
              if (edRef.current && document.contains(edRef.current)) {
                edRef.current.innerHTML = ''
                caretToEnd(edRef.current)
              }
            } catch(e) {}
            setCtxSel([]); setTyped('')
            // 同步清空草稿（发送成功，切 tab 回来不应恢复旧内容）
            __chatDraft.html = ''; __chatDraft.ctx = []
            try { if (window.__chatUpdatePh) window.__chatUpdatePh() } catch(e) {}
            setSending(false)
          }
          var unsub = null
          if (focused && typeof focused.subscribe === 'function') {
            // 已进入（Hermes 可能在 prompt.submit 后已自动聚焦）→ 延迟 200ms 结束
            try { if (focused.get() === storedId) { setTimeout(stop, 200); return } } catch(e) {}
            unsub = focused.subscribe(function(v) {
              if (v === storedId) setTimeout(stop, 200)
            })
            // 兜底：800ms 内 Hermes 没自动聚焦 → 补 openSession 跳转
            setTimeout(function() {
              if (!done) {
                try { if (focused.get() !== storedId) doNav() } catch(e) { doNav() }
              }
            }, 800)
            // 总兜底：8s 后无论如何结束
            setTimeout(stop, 8000)
          } else {
            // 无订阅能力：导航后给渲染留时间
            doNav()
            setTimeout(stop, 2200)
          }
        }
        function submitAndNav() {
          if (promptText) {
            host.request('prompt.submit', { session_id: runtimeId || storedId, text: promptText })
              .then(finish)
              .catch(function(e) {
                console.error('[pw] prompt.submit failed:', e)
                finish()
              })
          } else {
            finish()
          }
        }
        setTimeout(submitAndNav, 1500)
      })
      }) // cwdSetP.then 结束
    }).catch(function(e) { console.error('[pw] session.create failed:', e); setSending(false); R.tost('创建会话失败') })
    }, 500)
  }

  // ── 上传文件：选择文件 → 文件名作为 chip 加入输入框（发送时 attach） ──
  var fileInputRef = useRef(null)
  function doPickFile() {
    setPlusOpen(false); setPlusSub(null)
    try {
      if (!fileInputRef.current) {
        var fi = document.createElement('input')
        fi.type = 'file'
        fi.style.display = 'none'
        fi.addEventListener('change', function() {
          var f = fi.files && fi.files[0]
          if (!f) return
          // 绝对路径：优先 Hermes 桌面端 webUtils API（input[type=file] 的 f.path 已被 Chromium 移除）
          var p = ''
          try { if (window.hermesDesktop && window.hermesDesktop.getPathForFile) p = window.hermesDesktop.getPathForFile(f) } catch(e) {}
          if (!p && f.path) p = f.path
          if (!p) p = f.name  // 兜底：至少保留文件名（attach 时可能失败，但用户可见）
          var nm = f.name
          // 作为 file chip 加入上下文
          addCtxFrom({ type: 'file', name: nm, dir: '', path: p }, stRef.current.ctxSel || [])
          fi.value = ''
        })
        document.body.appendChild(fi)
        fileInputRef.current = fi
      }
      fileInputRef.current.click()
    } catch(e) { console.error('[pw] pick file failed:', e) }
  }

  // ── 指令选择：填入编辑器 ──
  function pickCmd(c) {
    var ed = edRef.current
    if (!ed) return
    // 剥离 frontmatter（--- 区块），只注入正文
    var raw = (c.content || '')
    var body = raw
    var fmMatch = raw.match(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/)
    if (fmMatch) body = raw.slice(fmMatch[0].length)
    body = body.trim()
    // 注入到光标处（保留已有 chip 和文本，不覆盖 @ 的内容）
    var sel = window.getSelection()
    var inserted = false
    var txt = null
    if (sel && sel.rangeCount && ed.contains(sel.anchorNode)) {
      var r = sel.getRangeAt(0)
      r.deleteContents()
      txt = document.createTextNode(body)
      r.insertNode(txt)
      r.setStartAfter(txt); r.collapse(true)
      sel.removeAllRanges(); sel.addRange(r)
      inserted = true
    }
    if (!inserted) {
      txt = document.createTextNode(body)
      ed.appendChild(txt)
      caretToEnd(ed)
    }
    // 移除残留的 ! 唤醒符：只删"非指令正文"的文本节点里的 !（正文本身的 ! 保留）
    var tw2 = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT)
    while (tw2.nextNode()) {
      var n2 = tw2.currentNode
      if (n2 === txt) continue // 跳过刚插入的正文
      var nv2 = n2.nodeValue || ''
      if (nv2.indexOf('!') >= 0) n2.nodeValue = nv2.split('!').join('')
    }
    setTyped(getEditorText(ed))
    // 同步草稿 + placeholder
    try { __chatDraft.html = ed.innerHTML } catch(e) {}
    try { if (window.__chatUpdatePh) window.__chatUpdatePh() } catch(e) {}
    ed.focus()
    setCmdPanel(false)
  }

  // ── @ 面板 ──
  function addCtx_impl(item, base) {
    var ns = base.concat([item])
    setCtxSel(ns)
    __chatDraft.ctx = ns
    setAtOpen(false); setAtQuery('')
    var ed = edRef.current
    if (ed) {
      var walk = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT)
      var tnodes = []
      while (walk.nextNode()) tnodes.push(walk.currentNode)
      var found = false
      for (var k = tnodes.length - 1; k >= 0; k--) {
        var tv = tnodes[k].nodeValue || ''
        var ix = tv.lastIndexOf('@')
        if (ix >= 0) {
          tnodes[k].nodeValue = tv.slice(0, ix)
          var chip = chipNode(item, ns.length - 1)
          var r = document.createRange()
          r.setStart(tnodes[k], ix); r.setEnd(tnodes[k], ix)
          r.insertNode(chip)
          var s2 = window.getSelection()
          var r2 = document.createRange()
          r2.setStartAfter(chip); r2.collapse(true)
          s2.removeAllRanges(); s2.addRange(r2)
          found = true
          break
        }
      }
      if (!found) { ed.appendChild(chipNode(item, ns.length - 1)); caretToEnd(ed) }
      setTyped(getEditorText(ed))
      // chip 插入后同步草稿（保序 html）
      try { __chatDraft.html = ed.innerHTML } catch(e) {}
      try { if (window.__chatUpdatePh) window.__chatUpdatePh() } catch(e) {}
      ed.focus()
    }
  }
  // 鼠标点击：React 渲染闭包 ctxSel 最新
  function addCtx(item) { addCtx_impl(item, ctxSel) }
  // 键盘选择：keydown 闭包固化，需传 stRef 最新 ctxSel
  function addCtxFrom(item, baseCtx) { addCtx_impl(item, baseCtx || ctxSel) }
  function rmCtx(i) {
    // 用 stRef.current.ctxSel 最新值（chip 的 onclick 闭包固化，避免旧 ctxSel 错乱）
    var cur = (stRef.current && stRef.current.ctxSel) || []
    var ns = cur.slice(); ns.splice(i, 1)
    setCtxSel(ns)
    __chatDraft.ctx = ns
    // 只删除目标 chip 节点，保留其他 chip 和文本的原始混排位置（不重建）
    var ed = edRef.current
    if (ed) {
      var chipEls = ed.querySelectorAll('[data-chip-idx]')
      if (chipEls[i]) { chipEls[i].remove() }
      // 剩余 chips 的 data-chip-idx 重排（保持 DOM 顺序一致）
      ed.querySelectorAll('[data-chip-idx]').forEach(function(n, j) { n.setAttribute('data-chip-idx', String(j)) })
      setTyped(getEditorText(ed))
      try { __chatDraft.html = ed.innerHTML } catch(e) {}
      try { if (window.__chatUpdatePh) window.__chatUpdatePh() } catch(e) {}
    }
  }
  function openAt() { setAtOpen(true); setCmdPanel(false); setSlashOpen(false); setAtQuery(''); setAtIdx(0) }
  function openCmds() { setCmdPanel(true); setAtOpen(false); setSlashOpen(false) }
  // ── / skills 面板 ──
  function loadSkills() {
    try {
      host.request('commands.catalog').then(function(cat) {
        var list = []
        var pairs = (cat && cat.pairs) || []
        // 只取 skill 扩展命令（/ 开头，非 Hermes built-in）
        pairs.forEach(function(p) {
          var cmd = p && p[0] ? String(p[0]) : ''
          if (cmd && cmd.indexOf('/') === 0) list.push({ cmd: cmd, meta: (p[1] || '') })
        })
        // 去重
        var seen = {}, uniq = []
        list.forEach(function(s) { if (!seen[s.cmd]) { seen[s.cmd] = 1; uniq.push(s) } })
        setSkills(uniq)
      }).catch(function(e) { console.error('[pw] commands.catalog failed:', e) })
    } catch(e) { console.error('[pw] loadSkills err:', e) }
  }
  function openSlash() { setSlashOpen(true); setAtOpen(false); setCmdPanel(false); setSlashQuery(''); setSlashIdx(0) }
  // / 面板选中项插入 /cmd 文本到光标处
  function insertSlash(cmd) {
    setSlashOpen(false); setSlashQuery('')
    var ed = edRef.current
    if (!ed) return
    // 用纯文本方式：替换光标前最后一个 "/" 及其后内容
    var plain = ''
    try { plain = getEditorPlainText(ed) } catch(e) {}
    var si = plain.lastIndexOf('/')
    var sel = window.getSelection && window.getSelection()
    // 简单可靠：重建纯文本（无 chip 时；有 chip 时保留 DOM，仅替换文本节点）
    var walk = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT)
    var tnodes = []
    while (walk.nextNode()) tnodes.push(walk.currentNode)
    if (tnodes.length) {
      var last = tnodes[tnodes.length - 1]
      var v = last.nodeValue || ''
      var ix = v.lastIndexOf('/')
      if (ix >= 0) {
        last.nodeValue = v.slice(0, ix) + cmd + ' '
        // 光标移到插入后
        var r = document.createRange(); r.setStart(last, (v.slice(0, ix) + cmd + ' ').length); r.collapse(true)
        var s2 = window.getSelection(); s2.removeAllRanges(); s2.addRange(r)
      }
    }
    setTyped(getEditorText(ed))
    try { __chatDraft.html = ed.innerHTML } catch(e) {}
    try { if (window.__chatUpdatePh) window.__chatUpdatePh() } catch(e) {}
    ed.focus()
  }
  // / 面板键盘导航
  function slashKeyNav(e) {
    var list = stRef.current.slashList || []
    var idx = stRef.current.slashIdx || 0
    if (e.key === 'ArrowDown') { e.preventDefault(); var nd = Math.min(idx + 1, list.length - 1); setSlashIdx(nd); scrollSlashSel(nd); return true }
    if (e.key === 'ArrowUp') { e.preventDefault(); var nu = Math.max(idx - 1, 0); setSlashIdx(nu); scrollSlashSel(nu); return true }
    if (e.key === 'Enter' && list.length > 0) { e.preventDefault(); if (list[idx]) insertSlash(list[idx].cmd); return true }
    if (e.key === 'Escape') { e.preventDefault(); setSlashOpen(false); setSlashQuery(''); return true }
    return false
  }
  // / 面板选中项滚动
  function scrollSlashSel(idx) {
    setTimeout(function() {
      var el = document.getElementById('slash-item-' + idx)
      if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }, 30)
  }
  // @ 面板选中项滚动到可视区
  function scrollAtSel(idx) {
    setTimeout(function() {
      var el = document.getElementById('at-item-' + idx)
      if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }, 30)
  }

  // ── 数据准备 ──
  var projects = R.ps || []
  var issues = R.ts || []
  var atProjects = projects.filter(function(p) { return p.status !== 'Done' && p.status !== 'Dropped' && (!atQuery || (p.title || '').toLowerCase().indexOf(atQuery.toLowerCase()) >= 0 || (p.dir || '').toLowerCase().indexOf(atQuery.toLowerCase()) >= 0) })
  var atIssues = issues.filter(function(t) { return t.status !== 'Done' && t.status !== 'Dropped' && (!atQuery || (t.title || '').toLowerCase().indexOf(atQuery.toLowerCase()) >= 0) })
  var atInbox = (inboxItems || []).filter(function(it) { return (!atQuery || (it.title || '').toLowerCase().indexOf(atQuery.toLowerCase()) >= 0) })
  var atList = atIssues.map(function(t) { return { kind: 'issue', item: t } }).concat(atProjects.map(function(p) { return { kind: 'project', item: p } })).concat(atInbox.map(function(it) { return { kind: 'inbox', item: it } }))
  stRef.current.atList = atList
  // / skills 面板：按 slashQuery 过滤（命令名 + meta）
  var filteredSkills = (skills || []).filter(function(s) {
    if (!slashQuery) return true
    var q = slashQuery.toLowerCase()
    return s.cmd.toLowerCase().indexOf(q) >= 0 || (s.meta || '').toLowerCase().indexOf(q) >= 0
  })
  stRef.current.slashList = filteredSkills
  var hasInput = (typed || '').trim().length > 0 || ctxSel.length > 0

  // ── 时间格式化 ──
  function fmtTime(ts) {
    if (!ts) return '—'
    var d = new Date(ts * 1000)
    var now = new Date()
    if (d.toDateString() === now.toDateString()) return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2)
    var yesterday = new Date(now); yesterday.setDate(now.getDate() - 1)
    if (d.toDateString() === yesterday.toDateString()) return '昨天'
    return ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2)
  }

  // ── @ 面板键盘选择（读 stRef 最新值，避免闭包固化） ──
  function atKeyNav(e) {
    var st = stRef.current
    var lst = st.atList || []
    if (e.key === 'ArrowDown') { e.preventDefault(); var nd = Math.min(st.atIdx + 1, lst.length - 1); setAtIdx(nd); scrollAtSel(nd); return true }
    if (e.key === 'ArrowUp') { e.preventDefault(); var nu = Math.max(st.atIdx - 1, 0); setAtIdx(nu); scrollAtSel(nu); return true }
    if (e.key === 'Enter' && lst.length > 0) {
      e.preventDefault()
      var sel = lst[Math.min(st.atIdx, lst.length - 1)]
      // 用 stRef.current.ctxSel 最新值（keydown 闭包固化，避免旧 ctxSel 覆盖）
      // 注意：st 已是 stRef.current（line 881），直接用 st.ctxSel
      var curCtx = st.ctxSel || []
      if (sel.kind === 'project') addCtxFrom({ type: 'project', name: sel.item.title, dir: sel.item.dir || sel.item.title, path: sel.item.path }, curCtx)
      else if (sel.kind === 'inbox') addCtxFrom({ type: 'inbox', name: sel.item.title, dir: '', path: sel.item.path, inbox_ts: sel.item.ts }, curCtx)
      else addCtxFrom({ type: 'issue', name: sel.item.title, dir: sel.item.dir, path: sel.item.path, project: sel.item.project, goal: sel.item.goal, task_detail: sel.item.task_detail, acceptance_criteria: sel.item.acceptance_criteria }, curCtx)
      return true
    }
    if (e.key === 'Escape') { e.preventDefault(); setAtOpen(false); return true }
    return false
  }

  // 三动物 SVG（虎猴兔）——可复用：吉祥物容器 + 对话框内预览
  function mascotSVGs(sz) {
    var w = sz || 27, h = Math.round((sz || 27) * 52 / 36)
    return [
      // 老虎
      jsx('svg', { style: { flexShrink: 0, display: 'block' }, width: w + '', height: h + '', viewBox: '0 0 36 52', preserveAspectRatio: 'xMidYMid meet', fill: 'none', children: [
        jsx('circle', { cx: '9', cy: '5', r: '4.5', fill: '#f59e0b' }),
        jsx('circle', { cx: '9', cy: '5', r: '2.2', fill: '#fbbf24' }),
        jsx('circle', { cx: '27', cy: '5', r: '4.5', fill: '#f59e0b' }),
        jsx('circle', { cx: '27', cy: '5', r: '2.2', fill: '#fbbf24' }),
        jsx('path', { d: 'M5 13 C5 5 14 3 18 3 C22 3 31 5 31 13 L31 29 C31 39 24 49 18 49 C12 49 5 39 5 29 Z', fill: '#fbbf24' }),
        jsx('path', { d: 'M13 24 Q18 20 23 24 L23 34 Q18 39 13 34 Z', fill: '#fff7ed' }),
        jsx('path', { d: 'M15 7 L21 7 M16 9.5 L20 9.5 M17.5 12 L18.5 12', stroke: '#d97706', strokeWidth: '1', strokeLinecap: 'round' }),
        jsx('circle', { cx: '12', cy: '18', r: '2.8', fill: '#1c1917' }),
        jsx('circle', { cx: '13', cy: '17', r: '0.9', fill: '#fff' }),
        jsx('circle', { cx: '24', cy: '18', r: '2.8', fill: '#1c1917' }),
        jsx('circle', { cx: '25', cy: '17', r: '0.9', fill: '#fff' }),
        jsx('path', { d: 'M17 25 L19 25 L18 27 Z', fill: '#d97706' }),
        jsx('path', { d: 'M16 29 Q18 31 18 30 Q18 31 20 29', stroke: '#d97706', strokeWidth: '1.2', strokeLinecap: 'round', fill: 'none' }),
        jsx('path', { d: 'M6 16 L9 18 M5.5 19 L8.5 21 M6 22 L9 23', stroke: '#d97706', strokeWidth: '1', strokeLinecap: 'round' }),
        jsx('path', { d: 'M30 16 L27 18 M30.5 19 L27.5 21 M30 22 L27 23', stroke: '#d97706', strokeWidth: '1', strokeLinecap: 'round' }),
      ]}),
      // 猴子
      jsx('svg', { style: { flexShrink: 0, display: 'block' }, width: w + '', height: h + '', viewBox: '0 0 36 52', preserveAspectRatio: 'xMidYMid meet', fill: 'none', children: [
        jsx('circle', { cx: '7', cy: '8', r: '5', fill: '#d6a06a' }),
        jsx('circle', { cx: '7', cy: '8', r: '3', fill: '#c08457' }),
        jsx('circle', { cx: '29', cy: '8', r: '5', fill: '#d6a06a' }),
        jsx('circle', { cx: '29', cy: '8', r: '3', fill: '#c08457' }),
        jsx('path', { d: 'M5 14 C5 6 14 4 18 4 C22 4 31 6 31 14 L31 30 C31 40 24 50 18 50 C12 50 5 40 5 30 Z', fill: '#d6a06a' }),
        jsx('path', { d: 'M18 16 C13 12 8 16 8 22 C8 29 18 38 18 38 C18 38 28 29 28 22 C28 16 23 12 18 16 Z', fill: '#fde8d0' }),
        jsx('circle', { cx: '13', cy: '21', r: '2.4', fill: '#1c1917' }),
        jsx('circle', { cx: '13.8', cy: '20.2', r: '0.8', fill: '#fff' }),
        jsx('circle', { cx: '23', cy: '21', r: '2.4', fill: '#1c1917' }),
        jsx('circle', { cx: '23.8', cy: '20.2', r: '0.8', fill: '#fff' }),
        jsx('circle', { cx: '18', cy: '27', r: '2.2', fill: '#c08457' }),
        jsx('path', { d: 'M15 31 Q18 34 21 31', stroke: '#92400e', strokeWidth: '1.2', strokeLinecap: 'round', fill: 'none' }),
      ]}),
      // 兔子
      jsx('svg', { style: { flexShrink: 0, display: 'block' }, width: w + '', height: h + '', viewBox: '0 0 36 52', preserveAspectRatio: 'xMidYMid meet', fill: 'none', children: [
        jsx('path', { d: 'M11 12 C8 0 5 2 6 10 L9 16 Z', fill: '#e5e7eb' }),
        jsx('path', { d: 'M9 12 C8 6 6 6 7 10 L9 14 Z', fill: '#f9a8d4' }),
        jsx('path', { d: 'M25 12 C28 0 31 2 30 10 L27 16 Z', fill: '#e5e7eb' }),
        jsx('path', { d: 'M27 12 C28 6 30 6 29 10 L27 14 Z', fill: '#f9a8d4' }),
        jsx('path', { d: 'M6 11 C6 4 14 3 18 3 C22 3 30 4 30 11 L30 28 C30 39 24 48 18 48 C12 48 6 39 6 28 Z', fill: '#e5e7eb' }),
        jsx('path', { d: 'M14 21 Q18 18 22 21 L22 30 Q18 34 14 30 Z', fill: '#fff' }),
        jsx('circle', { cx: '12', cy: '17', r: '2.5', fill: '#1c1917' }),
        jsx('circle', { cx: '12.8', cy: '16.2', r: '0.8', fill: '#fff' }),
        jsx('circle', { cx: '24', cy: '17', r: '2.5', fill: '#1c1917' }),
        jsx('circle', { cx: '24.8', cy: '16.2', r: '0.8', fill: '#fff' }),
        jsx('path', { d: 'M17 23 L19 23 L18 25 Z', fill: '#f472b6' }),
        jsx('path', { d: 'M18 25 L18 28 M18 28 L15.5 30 M18 28 L20.5 30', stroke: '#a1a1aa', strokeWidth: '1', strokeLinecap: 'round', fill: 'none' }),
        jsx('circle', { cx: '9', cy: '22', r: '2', fill: '#fbcfe8', opacity: '0.8' }),
        jsx('circle', { cx: '27', cy: '22', r: '2', fill: '#fbcfe8', opacity: '0.8' }),
      ]}),
    ]
  }

  return jsxs(Fragment, { children: [
    jsx('div', { 'data-pw': '1', className: S.page, style: { background: PAGE }, children: jsx('div', { className: S.wrap, children: jsxs('div', { style: { maxWidth: '720px', margin: '0 auto', paddingTop: R.compact ? 'min(16vh, 60px)' : '14vh', position: 'relative' }, children: [
    // 顶部导航（灵感入口 + 刷新，去掉 Chat 文案）
    jsxs('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }, children: [
      jsx('span', {}),
      jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '4px' }, children: [
        jsx('span', { className: S.iconBtn, style: { color: MUT }, title: '灵感收集', onClick: function() { R.setMd('inbox') }, children: jsx(Codicon, { name: 'lightbulb', className: 'text-[0.9375rem]' }) }),
        jsx('span', { className: S.iconBtn, style: { color: MUT }, onClick: function() { loadRecents(); loadCmds(); R.load() }, children: jsx(Codicon, { name: 'refresh', className: 'text-[0.9375rem]' }) }),
      ]}),
    ]}),
    // 问候（手写体：Quillbacks Demo）
    jsx('div', { style: { textAlign: 'center' }, children: [
      jsx('div', { style: { fontSize: '40px', fontWeight: 500, marginBottom: '0px', color: INK, fontFamily: "'Quillbacks Demo', cursive", letterSpacing: '0.02em', lineHeight: 1.1 }, children: 'Hi, Ben' }),
      jsx('div', { style: { fontSize: '19px', color: MUT, marginBottom: '12px', fontFamily: "'Quillbacks Demo', cursive" }, children: 'What can I do for you today?' }),
    ]}),
    // 面板遮罩（zIndex 29 < 主对话卡 30，只拦截卡片外点击）
    (atOpen || cmdPanel || slashOpen) && jsx('div', { style: { position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 29, background: 'transparent' }, onClick: function() { setAtOpen(false); setCmdPanel(false); setSlashOpen(false) } }),
    // 小吉祥物：虎猴兔三动物（外部图片，26px=原40px的65%）
    // 初始只露 25%（向下 75%），hover 露出 55%；位置由 useEffect 测量主对话卡上沿后设置（不猜像素）
    jsx('div', {
      ref: mascotRef,
      style: { position: 'absolute', top: '60px', right: '14px', width: 'max-content', height: '26px', zIndex: 28, cursor: 'pointer', display: sending ? 'none' : 'flex', alignItems: 'flex-end', justifyContent: 'flex-start', opacity: sending ? 0 : 1, transition: 'opacity 0.25s ease' },
      onMouseEnter: function(e) { var c = e.currentTarget.firstChild; if (c) c.style.transform = 'translateY(-7.8px)' },
      onMouseLeave: function(e) { var c = e.currentTarget.firstChild; if (c) c.style.transform = 'translateY(0)' },
      children: jsx('div', { style: { display: 'flex', alignItems: 'flex-end', gap: '0.5px', transform: 'translateY(0)', transition: 'transform 0.3s ease' }, children: [
        jsx('img', { key: 't', src: ASSET_DIR + 'tiger.svg', style: { width: '26px', height: '26px', display: 'block' } }),
        jsx('img', { key: 'm', src: ASSET_DIR + 'monkey.svg', style: { width: '26px', height: '26px', display: 'block' } }),
        jsx('img', { key: 'r', src: ASSET_DIR + encodeURIComponent('小兔子.svg'), style: { width: '26px', height: '26px', display: 'block' } }),
      ] }),
    }),
    // 主对话卡（sending 时整体变灰 + 过渡）。zIndex 30 高于遮罩 29 与吉祥物 28：卡片覆盖猫下半，只露耳朵
    jsxs('div', { ref: chatCardRef, style: { background: SURF, borderRadius: '16px', boxShadow: SH_CARD, padding: '16px 18px', textAlign: 'left', position: 'relative', zIndex: 30, transition: 'opacity 0.3s ease, background 0.3s ease', opacity: sending ? 0.55 : 1, background: sending ? '#f2f3f4' : SURF, pointerEvents: sending ? 'none' : 'auto' }, children: [
      // 输入区：React 只渲染空容器，原生 contenteditable 由 useEffect 挂入
      jsx('div', { ref: wrapRef, style: { position: 'relative', minHeight: '101px', cursor: 'text' } }),
      // @ 选择面板（ref：外部点击关闭判断用；zIndex 30 高于任何残留遮罩）
      atOpen && jsx('div', { ref: atPanelRef, style: { position: 'relative', zIndex: 30, borderTop: '1px solid ' + HOV, margin: '10px -4px 0', padding: '10px 4px 6px' }, children: jsxs('div', { children: [
        jsx('div', { style: { padding: '0 2px 10px', fontSize: '13px', color: MUT, borderBottom: '1px solid ' + HOV }, children: '输入 @' + (atQuery || '') + ' 继续筛选…' }),
        jsx('div', { style: { overflowY: 'auto', minHeight: 0, maxHeight: '250px' }, children: [
          jsx('div', { style: { padding: '8px 2px 2px', fontSize: '10px', letterSpacing: '0.08em', color: MUT, fontWeight: 600 }, children: 'ISSUES' }),
          atIssues.length === 0 ? jsx('div', { style: { padding: '4px 2px 10px', fontSize: '11.5px', color: FAINT }, children: '无匹配 Issue' }) : atIssues.map(function(t, ti) {
            return jsxs('div', { id: 'at-item-' + ti, style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 2px', borderRadius: '6px', cursor: 'pointer', background: atIdx === ti ? HOV : 'transparent' }, onClick: function() { addCtx({ type: 'issue', name: t.title, dir: t.dir, path: t.path, project: t.project, goal: t.goal, task_detail: t.task_detail, acceptance_criteria: t.acceptance_criteria }) }, children: [
              jsx('span', { style: { width: '22px', height: '22px', borderRadius: '6px', background: ACCS, color: ACC, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', flexShrink: 0 }, children: (t.title || '?').charAt(0) }),
              jsx('span', { style: { flex: 1, fontSize: '13px', color: INK, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, children: t.title }),
              jsx('span', { style: { fontSize: '11px', color: FAINT }, children: (t.project || t.dir) || '' }),
            ]}, 'i' + t.path)
          }),
          jsx('div', { style: { padding: '8px 2px 2px', fontSize: '10px', letterSpacing: '0.08em', color: MUT, fontWeight: 600 }, children: 'PROJECTS' }),
          atProjects.length === 0 ? jsx('div', { style: { padding: '4px 2px 10px', fontSize: '11.5px', color: FAINT }, children: '无匹配项目' }) : atProjects.map(function(p, pi) {
            var flatIdx = atIssues.length + pi
            return jsxs('div', { id: 'at-item-' + flatIdx, style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 2px', borderRadius: '6px', cursor: 'pointer', background: atIdx === flatIdx ? HOV : 'transparent' }, onClick: function() { addCtx({ type: 'project', name: p.title, dir: p.dir || p.title, path: p.path }) }, children: [
              jsx('span', { style: { width: '22px', height: '22px', borderRadius: '6px', background: PURPLE_T, color: PURPLE, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', flexShrink: 0 }, children: (p.title || '?').charAt(0) }),
              jsx('span', { style: { flex: 1, fontSize: '13px', color: INK, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, children: p.title }),
              jsx('span', { style: { fontSize: '11px', color: FAINT }, children: '项目' }),
            ]}, 'p' + p.dir)
          }),
          jsx('div', { style: { padding: '8px 2px 2px', fontSize: '10px', letterSpacing: '0.08em', color: MUT, fontWeight: 600 }, children: 'INBOX' }),
          atInbox.length === 0 ? jsx('div', { style: { padding: '4px 2px 10px', fontSize: '11.5px', color: FAINT }, children: '无匹配收集' }) : atInbox.map(function(it, xi) {
            var flatIdx = atIssues.length + atProjects.length + xi
            return jsxs('div', { id: 'at-item-' + flatIdx, style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 2px', borderRadius: '6px', cursor: 'pointer', background: atIdx === flatIdx ? HOV : 'transparent' }, onClick: function() { addCtx({ type: 'inbox', name: it.title, dir: '', path: it.path, inbox_ts: it.ts }) }, children: [
              jsx('span', { style: { width: '22px', height: '22px', borderRadius: '6px', background: ORANGE_T, color: ORANGE, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', flexShrink: 0 }, children: (it.title || '?').charAt(0) }),
              jsx('span', { style: { flex: 1, fontSize: '13px', color: INK, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, children: it.title }),
              jsx('span', { style: { fontSize: '11px', color: FAINT }, children: 'Inbox' }),
            ]}, 'x' + it.path)
          }),
        ]}),
      ]}) }),
      // 指令面板
      cmdPanel && jsx('div', { ref: cmdPanelRef, style: { position: 'relative', zIndex: 30, borderTop: '1px solid ' + HOV, margin: '10px -4px 0', padding: '10px 4px 6px' }, children: jsxs('div', { children: [
        jsx('div', { style: { padding: '0 2px 10px', fontSize: '13px', fontWeight: 600, color: INK, borderBottom: '1px solid ' + HOV }, children: 'Quick Commands' }),
        jsx('div', { style: { overflowY: 'auto', minHeight: 0, maxHeight: '250px' }, children: [
          cmds.length === 0 ? jsx('div', { style: { padding: '14px', fontSize: '12px', color: FAINT }, children: '暂无指令，可在 2. Project/commands/ 下添加 .md 文件' }) : cmds.map(function(c) {
            return jsxs('div', { className: 'pw-hover', style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 2px', borderRadius: '6px', cursor: 'pointer' }, onClick: function() { pickCmd(c) }, children: [
              jsx('span', { style: { color: ACC, fontSize: '12px', flexShrink: 0 }, children: '!' }),
              jsx('span', { style: { flex: 1, minWidth: 0, fontSize: '13px', fontWeight: 500, color: INK, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, children: c.title }),
            ]}, 'c' + c.name)
          }),
        ]}),
      ]}) }),
      // / skills 面板
      slashOpen && jsx('div', { ref: cmdPanelRef, style: { position: 'relative', zIndex: 30, borderTop: '1px solid ' + HOV, margin: '10px -4px 0', padding: '10px 4px 6px' }, children: jsxs('div', { children: [
        jsx('div', { style: { padding: '0 2px 10px', fontSize: '13px', fontWeight: 600, color: INK, borderBottom: '1px solid ' + HOV }, children: 'Skills（/ 唤起）' }),
        jsx('div', { style: { overflowY: 'auto', minHeight: 0, maxHeight: '250px' }, children: [
          filteredSkills.length === 0 ? jsx('div', { style: { padding: '14px', fontSize: '12px', color: FAINT }, children: '暂无匹配的 Skill' }) : filteredSkills.map(function(s, si) {
            var sel = si === slashIdx
            return jsxs('div', { id: 'slash-item-' + si, style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 2px', borderRadius: '6px', cursor: 'pointer', background: sel ? HOV : 'transparent' }, onMouseEnter: function() { setSlashIdx(si) }, onClick: function() { insertSlash(s.cmd) }, children: [
              jsx('span', { style: { color: PURPLE, fontSize: '12px', flexShrink: 0, fontWeight: 500 }, children: '/' }),
              jsx('span', { style: { flex: 1, minWidth: 0, fontSize: '13px', fontWeight: 500, color: INK, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, children: s.cmd.indexOf('/') === 0 ? s.cmd.slice(1) : s.cmd }),
              s.meta ? jsx('span', { style: { fontSize: '11px', color: FAINT, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '160px' }, children: s.meta }) : null,
            ]}, 's' + (s.cmd || si))
          }),
        ]}),
      ]}) }),
      // 底部：+ 菜单 + 发送（行高紧凑，给 chat 主框留更多空间）
      jsxs('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '6px', paddingTop: '6px', borderTop: '1px solid ' + HOV, position: 'relative' }, children: [
        jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '6px' }, children: [
          // 单个 + 按钮（唤起附加菜单）
          jsx('span', { className: 'pw-plus-btn', style: { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: '22px', height: '22px', borderRadius: '7px', background: plusOpen ? SBG : INSET, color: BODY, fontSize: '15px', lineHeight: 1, cursor: 'pointer' }, onClick: function() {
            if (!plusOpen && window.__pwNeedReloadCmds) { window.__pwNeedReloadCmds = false; loadCmds() }
            setPlusOpen(!plusOpen); setPlusSub(null)
          }, children: '+' }),
        ]}),
        jsx('button', { type: 'submit', className: 'flex items-center justify-center shrink-0 cursor-pointer transition-all', style: { width: '26px', height: '26px', borderRadius: '99px', background: sending ? '#9aa5b1' : (hasInput ? ACC : OPEN_DOT), color: '#fff', border: 'none', padding: 0, opacity: sending ? 1 : (hasInput ? 1 : 0.6), cursor: sending ? 'default' : 'pointer' }, onClick: doSend, children: sending ? jsx(Codicon, { name: 'loading', className: 'animate-spin', size: '0.875rem' }) : jsx(Codicon, { name: 'arrow-up', size: '0.875rem' }) }),
        // + 附加菜单（白色圆角卡片 + 投影，照抄截图形式）
        plusOpen && jsxs('div', { 'data-plus-menu': '1', style: { position: 'absolute', bottom: '100%', left: 0, marginBottom: '8px', background: '#fff', borderRadius: '18px', boxShadow: '0 4px 24px rgba(0,0,0,0.12), 0 1px 4px rgba(0,0,0,0.06)', padding: '6px', minWidth: '240px', zIndex: 40, fontFamily: 'inherit' }, children: [
          // Add files or photos
          jsxs('div', { className: 'pw-hover', style: { display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 10px', borderRadius: '10px', cursor: 'pointer' }, onClick: function() { doPickFile() }, children: [
            jsx('span', { style: { display: 'inline-flex', width: '18px', height: '18px', alignItems: 'center', justifyContent: 'center', color: INK }, children: jsx(Codicon, { name: 'attach', size: '0.875rem' }) }),
            jsx('span', { style: { flex: 1, fontSize: '13px', color: INK }, children: 'Add files or photos' }),
            jsx('span', { style: { fontSize: '11px', color: FAINT }, children: '⌘U' }),
          ]}),
          // Add to project（二级菜单）
          jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 10px', borderRadius: '10px', cursor: 'pointer', background: plusSub === 'projects' ? HOV : 'transparent' }, onMouseEnter: function(e) { e.currentTarget.style.background = HOV; setPlusSub('projects') }, onMouseLeave: function(e) { e.currentTarget.style.background = plusSub === 'projects' ? HOV : 'transparent' }, children: [
            jsx('span', { style: { display: 'inline-flex', width: '18px', height: '18px', alignItems: 'center', justifyContent: 'center', color: INK }, children: jsx(Codicon, { name: 'briefcase', size: '0.875rem' }) }),
            jsx('span', { style: { flex: 1, fontSize: '13px', color: INK }, children: 'Add to Project' }),
            jsx('span', { style: { fontSize: '11px', color: FAINT }, children: '›' }),
          ]}),
          // Add to Issue（二级菜单）
          jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 10px', borderRadius: '10px', cursor: 'pointer', background: plusSub === 'issues' ? HOV : 'transparent' }, onMouseEnter: function(e) { e.currentTarget.style.background = HOV; setPlusSub('issues') }, onMouseLeave: function(e) { e.currentTarget.style.background = plusSub === 'issues' ? HOV : 'transparent' }, children: [
            jsx('span', { style: { display: 'inline-flex', width: '18px', height: '18px', alignItems: 'center', justifyContent: 'center', color: INK }, children: jsx(Codicon, { name: 'tasklist', size: '0.875rem' }) }),
            jsx('span', { style: { flex: 1, fontSize: '13px', color: INK }, children: 'Add to Issue' }),
            jsx('span', { style: { fontSize: '11px', color: FAINT }, children: '›' }),
          ]}),
          // Quick Commands（二级菜单）
          jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 10px', borderRadius: '10px', cursor: 'pointer', background: plusSub === 'cmds' ? HOV : 'transparent' }, onMouseEnter: function(e) { e.currentTarget.style.background = HOV; setPlusSub('cmds') }, onMouseLeave: function(e) { e.currentTarget.style.background = plusSub === 'cmds' ? HOV : 'transparent' }, children: [
            jsx('span', { style: { display: 'inline-flex', width: '18px', height: '18px', alignItems: 'center', justifyContent: 'center', color: INK }, children: jsx(Codicon, { name: 'zap', size: '0.875rem' }) }),
            jsx('span', { style: { flex: 1, fontSize: '13px', color: INK }, children: 'Quick Commands' }),
            jsx('span', { style: { fontSize: '11px', color: FAINT }, children: '›' }),
          ]}),
        ]}),
        // 二级菜单：项目列表（Add to project 展开，排除已完成/已放弃）
        plusOpen && plusSub === 'projects' && jsxs('div', { 'data-plus-menu': '1', style: { position: 'absolute', bottom: '100%', left: '250px', marginBottom: '8px', background: '#fff', borderRadius: '18px', boxShadow: '0 4px 24px rgba(0,0,0,0.12), 0 1px 4px rgba(0,0,0,0.06)', padding: '6px', width: '280px', zIndex: 41, fontFamily: 'inherit', maxHeight: '320px', overflowY: 'auto' }, children: [
          jsxs('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 10px' }, children: [
            jsx('span', { style: { fontSize: '12px', color: FAINT }, children: '选择项目作为上下文' }),
            jsx('span', { style: { fontSize: '11px', color: ACC, cursor: 'pointer', fontWeight: 500 }, onClick: function() { setPlusOpen(false); setPlusSub(null); R.setMd('project') }, children: '+ New' }),
          ]}),
          jsx('div', { style: { borderTop: '1px solid ' + DIVIDER, margin: '4px 0' } }),
          (R.ps || []).filter(function(p) { return p.status !== 'Done' && p.status !== 'Dropped' }).slice(0, 10).map(function(p) {
            return jsxs('div', { className: 'pw-hover', style: { display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 10px', borderRadius: '10px', cursor: 'pointer' }, onClick: function() { setPlusOpen(false); setPlusSub(null); addCtx({ type: 'project', name: p.title || p.dir, dir: p.dir || p.title, path: p.path }) }, children: [
              jsx('span', { style: { display: 'inline-flex', width: '18px', height: '18px', alignItems: 'center', justifyContent: 'center', color: MUT }, children: jsx(Codicon, { name: 'briefcase', size: '0.875rem' }) }),
              jsx('span', { style: { flex: 1, fontSize: '13px', color: INK, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, children: p.title || p.dir }),
            ]}, 'pj' + (p.path || p.title))
          }),
        ]}),
        // 二级菜单：快捷指令列表（Quick Commands 展开）
        plusOpen && plusSub === 'cmds' && jsxs('div', { 'data-plus-menu': '1', style: { position: 'absolute', bottom: '100%', left: '250px', marginBottom: '8px', background: '#fff', borderRadius: '18px', boxShadow: '0 4px 24px rgba(0,0,0,0.12), 0 1px 4px rgba(0,0,0,0.06)', padding: '6px', width: '280px', zIndex: 41, fontFamily: 'inherit', maxHeight: '320px', overflowY: 'auto' }, children: [
          jsxs('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 10px' }, children: [
            jsx('span', { style: { fontSize: '12px', color: FAINT }, children: '选择快捷指令' }),
            jsx('span', { style: { fontSize: '11px', color: ACC, cursor: 'pointer', fontWeight: 500 }, onClick: function() { setPlusOpen(false); setPlusSub(null); R.setMd('cmd') }, children: '+ New' }),
          ]}),
          jsx('div', { style: { borderTop: '1px solid ' + DIVIDER, margin: '4px 0' } }),
          cmds.length === 0 ? jsx('div', { style: { padding: '10px', fontSize: '12px', color: FAINT }, children: '暂无指令' }) : cmds.map(function(c) {
            return jsxs('div', { className: 'pw-hover', style: { display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 10px', borderRadius: '10px', cursor: 'pointer' }, onClick: function() { setPlusOpen(false); setPlusSub(null); pickCmd(c) }, children: [
              jsx('span', { style: { display: 'inline-flex', width: '18px', height: '18px', alignItems: 'center', justifyContent: 'center', color: ACC }, children: jsx(Codicon, { name: 'zap', size: '0.875rem' }) }),
              jsx('span', { style: { flex: 1, fontSize: '13px', color: INK, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, children: c.title }),
            ]}, 'cj' + (c.name || c.title))
          }),
        ]}),
        // 二级菜单：任务列表（Add to Issue 展开，排除已完成/已放弃）
        plusOpen && plusSub === 'issues' && jsxs('div', { 'data-plus-menu': '1', style: { position: 'absolute', bottom: '100%', left: '250px', marginBottom: '8px', background: '#fff', borderRadius: '18px', boxShadow: '0 4px 24px rgba(0,0,0,0.12), 0 1px 4px rgba(0,0,0,0.06)', padding: '6px', width: '280px', zIndex: 41, fontFamily: 'inherit', maxHeight: '320px', overflowY: 'auto' }, children: [
          jsxs('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 10px' }, children: [
            jsx('span', { style: { fontSize: '12px', color: FAINT }, children: '选择任务作为上下文' }),
            jsx('span', { style: { fontSize: '11px', color: ACC, cursor: 'pointer', fontWeight: 500 }, onClick: function() { setPlusOpen(false); setPlusSub(null); R.setMd('task') }, children: '+ New' }),
          ]}),
          jsx('div', { style: { borderTop: '1px solid ' + DIVIDER, margin: '4px 0' } }),
          (R.ts || []).filter(function(t) { return t.status !== 'Done' && t.status !== 'Dropped' }).slice(0, 12).map(function(t) {
            return jsxs('div', { className: 'pw-hover', style: { display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 10px', borderRadius: '10px', cursor: 'pointer' }, onClick: function() { setPlusOpen(false); setPlusSub(null); addCtx({ type: 'issue', name: t.title, dir: t.dir, path: t.path, project: t.project, goal: t.goal, task_detail: t.task_detail, acceptance_criteria: t.acceptance_criteria }) }, children: [
              jsx('span', { style: { display: 'inline-flex', width: '18px', height: '18px', alignItems: 'center', justifyContent: 'center', color: MUT }, children: jsx(Codicon, { name: 'tasklist', size: '0.875rem' }) }),
              jsx('span', { style: { flex: 1, fontSize: '13px', color: INK, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, children: t.title }),
              jsx('span', { style: { fontSize: '11px', color: FAINT, flexShrink: 0 }, children: (t.project || '') }),
            ]}, 'tj' + (t.path || t.title))
          }),
        ]}),
      ]}),
    ]}),
    // Recent Sessions 区块（去掉三 tab，纯标题 + sessions 列表；整体居中）
    jsxs('div', { style: { margin: '26px auto 0', textAlign: 'left', maxWidth: '700px' }, children: [
      // 标题（替代原 tab 栏）
      jsx('div', { style: { fontSize: '12.5px', color: MUT, fontWeight: 500, marginBottom: '10px', padding: '0 2px' }, children: 'Recent Sessions' }),
      // ── Sessions 列表 ──
      recentSess.length === 0
        ? jsx('div', { style: { padding: '10px 2px', fontSize: '12px', color: FAINT }, children: '暂无会话，先在上方输入任务开始吧' })
        : jsxs('div', { style: { height: '200px', overflowY: 'auto', overflowX: 'hidden', margin: '0 -4px', padding: '0 4px' }, className: 'rs-scroll', children: recentSess.map(function(s) {
            function jumpProject(ev, s2) {
              if (ev) ev.stopPropagation()
              var pjn = R.pj(s2.link.project) || (R.ps || []).filter(function(p) { return (p.dir || p.title) === s2.link.project })[0]
              if (pjn) { R.setSel(pjn.title); R.setVw('project') }
              else if (R.onExit) R.onExit('projects')
            }
            function jumpIssue(ev, s2) {
              if (ev) ev.stopPropagation()
              var t = (R.ts || []).filter(function(x) { return x.path === s2.link.issue_path })[0]
              if (R.onExit) R.onExit('board')
              if (t) { setTimeout(function() { R.setDw(t) }, 0) }
            }
            var link = s.link
            return jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '12px', padding: '3px 2px', borderRadius: '6px' }, children: [
              jsxs('div', { style: { width: '260px', flexShrink: 0, minWidth: 0, cursor: 'pointer' }, onClick: function() { host.navigate('/' + encodeURIComponent(s.id)) }, children: [
                jsx('span', { style: { display: 'block', fontSize: '12.5px', color: BODY, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, children: s.title }),
              ]}),
              jsx('span', { style: { flex: 1, minWidth: 0, fontSize: '11px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', cursor: link && link.project ? 'pointer' : 'default', color: link && link.project ? MUT : FAINT }, onClick: function(e) { if (link && link.project) jumpProject(e, s) }, children: link && link.project ? link.project : '—' }),
              jsx('span', { style: { flex: 1, minWidth: 0, fontSize: '11px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', cursor: link && link.issue_path ? 'pointer' : 'default', color: link && link.issue_path ? MUT : FAINT }, onClick: function(e) { if (link && link.issue_path) jumpIssue(e, s) }, children: link && link.issue_title ? link.issue_title : '—' }),
              jsx('span', { style: { width: '60px', flexShrink: 0, textAlign: 'right', fontSize: '10.5px', color: OPEN_DOT, fontVariantNumeric: 'tabular-nums' }, children: fmtTime(s.last_activity_at) }),
            ]}, s.id)
          }) })
    ]}),
  ]}) })}),
  ]})
}

// ─── Board View（首页全局任务看板）────────────────────────
// ─── Board View + List View（Issues 两视图，共用过滤模型）────
// 默认过滤（2026-09-02 更新）：仅截止日期=近7天，状态不设默认（全部状态可见）
var IW_DEF_FILTERS = { status: [], priority: [], handler: [], project: [], due: ['7d'] }
var IW_DUE_OPTS = [{ v: 'overdue', label: '已逾期' }, { v: '7d', label: '近7天' }, { v: '30d', label: '近30天' }]
var IW_STATUS_ORDER = ['open', 'In-Progress', 'Waiting', 'Agent', 'Review', 'Done', 'Dropped']
// 可筛选字段定义（处理人/项目可选值从当前任务集提取）
function issuesFilterDefs(R) {
  var handlers = [], projects = [], seenH = {}, seenP = {}
  R.ts.forEach(function(t) {
    if (t.handler && !seenH[t.handler]) { seenH[t.handler] = 1; handlers.push(t.handler) }
    if (t.project && !seenP[t.project]) { seenP[t.project] = 1; projects.push(t.project) }
  })
  return [
    { k: 'status', label: '状态', opts: IW_STATUS_ORDER.map(function(s) { return { v: s, label: PST[s] || s, dot: SDOT[s] } }) },
    { k: 'priority', label: '优先级', opts: ['p0', 'p1', 'p2'].map(function(p) { return { v: p, label: PR[p] || p } }) },
    { k: 'handler', label: '处理人', opts: handlers.map(function(h) { return { v: h, label: h } }) },
    { k: 'project', label: '项目', opts: projects.map(function(p) { return { v: p, label: p } }) },
    { k: 'due', label: '截止日期', opts: IW_DUE_OPTS },
  ]
}
// 字段值显示文案
function iwOptLabel(k, v) {
  if (k === 'status') return PST[v] || v
  if (k === 'due') { var o = IW_DUE_OPTS.find(function(x) { return x.v === v }); return o ? o.label : v }
  if (k === 'priority') return PR[v] || v
  return v
}
// 日期筛选口径：已完成/取消与无 due 不参与（与看板强调口径一致）；多选 OR。
// 窗口口径（用户确认 2026-08-31）：近N天 = 截止日期早于等于窗口终点（自然包含已逾期）；
// 已逾期作为独立选项供单独筛选。
function iwMatchDue(t, sel, today) {
  if (t.status === 'Done' || t.status === 'Dropped' || !t.due) return false
  for (var i = 0; i < sel.length; i++) {
    var o = sel[i]
    if (o === 'overdue' && t.due < today) return true
    if (o === '7d' && t.due <= addDaysLocal(7)) return true
    if (o === '30d' && t.due <= addDaysLocal(30)) return true
  }
  return false
}

function BoardView(R) {
  var today = todayLocal()
  // 过滤状态（两视图共用）：字段 → 已选值数组；默认 IW_DEF_FILTERS（近7天 + 非已完成）
  var fst = useState(function() { return JSON.parse(JSON.stringify(IW_DEF_FILTERS)) }), filters = fst[0], setFilters = fst[1]
  // 筛选菜单开合 + 二级子菜单展开的字段
  var mst = useState(false), menuOpen = mst[0], setMenuOpen = mst[1]
  var sbt = useState(null), openSub = sbt[0], setOpenSub = sbt[1]
  // 视图（session 内有效）：'board' | 'list'，默认 Board（2026-09-02 更新）
  var vst = useState('board'), view = vst[0], setView = vst[1]

  var defs = issuesFilterDefs(R)
  function hasFilters() { return defs.some(function(f) { return filters[f.k] && filters[f.k].length > 0 }) }
  var filtered = R.ts.filter(function(t) {
    if (filters.status.length && filters.status.indexOf(t.status) < 0) return false
    if (filters.priority.length && filters.priority.indexOf(t.priority) < 0) return false
    if (filters.handler.length && filters.handler.indexOf(t.handler) < 0) return false
    if (filters.project.length && filters.project.indexOf(t.project) < 0) return false
    if (filters.due.length && !iwMatchDue(t, filters.due, today)) return false
    return true
  })
  function toggleFilter(k, v) {
    var cur = filters[k] || [], i = cur.indexOf(v), ns = cur.slice()
    if (i >= 0) ns.splice(i, 1); else ns.push(v)
    var nf = Object.assign({}, filters); nf[k] = ns; setFilters(nf)
  }
  function clearField(k) { var nf = Object.assign({}, filters); nf[k] = []; setFilters(nf) }
  function clearAllFilters() { setFilters({ status: [], priority: [], handler: [], project: [], due: [] }) }

  // List 展示顺序 = 过滤后顺序（不做行排序/列排序/行选择）
  var listRows = filtered


  // List 表头列定义（列序用户确认 2026-08-31：Issue → 状态 → 截止日期 → 优先级 → 处理人 → 项目）
  var COLS = [
    { k: 'title', label: 'Issue', w: null },
    { k: 'status', label: '状态', w: '104px' },
    { k: 'due', label: '截止日期', w: '92px' },
    { k: 'priority', label: '优先级', w: '84px' },
    { k: 'handler', label: '处理人', w: '104px' },
    { k: 'project', label: '项目', w: '140px' },
  ]
  var tdStyle = { padding: '0 10px', height: '34px', fontSize: '0.8125rem', color: BODY, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }

  // List 视图：平铺表格（无框体、无横线），sticky 表头 + 行点击开抽屉
  // 精简版（用户确认 2026-08-31）：无排序、无行选择框；过滤计数并入 Issue 表头
  function listView() {
    var headCells = COLS.map(function(c) {
      return jsx('th', { key: c.k, style: { textAlign: 'left', fontSize: '0.6875rem', fontWeight: 500, color: MUT, padding: '0 10px', height: '34px', position: 'sticky', top: 0, background: '#fff', whiteSpace: 'nowrap', width: c.w || undefined }, children: c.k === 'title' ? (c.label + ' · ' + listRows.length) : c.label })
    })
    var bodyRows = listRows.map(function(t) {
      var overdue = dueFlag(t, today)
      return jsxs('tr', {
        className: 'cursor-pointer pw-hover',
        onClick: function() { R.setDw(t); R.setVw('task-detail') },
        children: [
          jsx('td', { key: 'title', style: tdStyle, children:
            jsxs('span', { className: 'inline-flex items-center gap-1.5', style: { maxWidth: '100%' }, children: [
              jsx('span', { className: 'truncate font-medium', style: { color: INK, fontSize: '0.8125rem' }, children: t.title }),
              t.repeat_mode ? jsx('span', { title: '重复周期任务：' + repLabel(t), style: { color: MUT, flexShrink: 0, fontSize: '11px' }, children: '🔁' }) : null,
            ] }),
          }),
          jsx('td', { key: 'status', style: tdStyle, children:
            jsxs('span', { className: 'inline-flex items-center gap-1.5', style: { fontSize: '0.75rem', color: BODY, whiteSpace: 'nowrap' }, children: [
              // 状态虚线圆环：字体 85% 大小（12px×0.85≈10px），中心透明，细虚线环色=状态语义色
              jsx('span', { style: { width: '10px', height: '10px', borderRadius: 99, border: '1px dashed ' + (SDOT[t.status] || FAINT), background: 'transparent', flexShrink: 0, display: 'inline-block' } }),
              jsx('span', { children: PST[t.status] || t.status }),
            ] }),
          }),
          jsx('td', { key: 'due', style: Object.assign({}, tdStyle, { color: overdue ? DANGER : MUT, fontWeight: overdue ? 500 : 400, fontSize: '0.75rem' }), children: t.due ? dL(t.due) : '—' }),
          jsx('td', { key: 'priority', style: Object.assign({}, tdStyle, { color: MUT, fontSize: '0.75rem' }), children: PR[t.priority] || t.priority || '—' }),
          jsx('td', { key: 'handler', style: Object.assign({}, tdStyle, { color: MUT, fontSize: '0.75rem' }), children: t.handler || '—' }),
          jsx('td', { key: 'project', style: Object.assign({}, tdStyle, { color: MUT, fontSize: '0.75rem' }), children: t.project || t.dir || '—' }),
        ],
      }, t.path)
    })
    return jsx('div', { children:
      jsx('table', { style: { width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }, children: [
        jsx('thead', { children: jsx('tr', { children: headCells }) }),
        jsx('tbody', { children: bodyRows.length === 0
          ? jsx('tr', { children: jsx('td', { colSpan: 6, style: { padding: '40px 0', textAlign: 'center', fontSize: '0.6875rem', color: FAINT }, children: 'No issues match the filter' }) })
          : bodyRows }),
      ]}),
    })
  }

  // 看板视图：6 列 = BOARD_GROUPS × 过滤后任务（列/卡片渲染复用共享原语 BoardColumn/TaskCard）
  function boardView() {
    return jsx('div', { className: 'flex gap-3 overflow-x-auto', style: { paddingBottom: '14px' }, children: BOARD_GROUPS.map(function(g) {
      var gt = filtered.filter(function(x) { return (g.match || [g.status]).indexOf(x.status) >= 0 })
      return jsx(BoardColumn, { key: g.status, g: g, tasks: gt, R: R, today: today, dropSource: filtered })
    }) })
  }

  return jsxs(Fragment, { children: [
    // 过滤行：大胶囊(已选项) + (弹性) + Clear + 筛选/视图切换圆按钮（RoundBtn 原语）
    jsxs('div', { style: { position: 'relative', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px', minHeight: '30px' }, children: [
      // 大胶囊：已选过滤条件集合（白底描边胶囊容器，与圆按钮做视觉区分）；空态虚线提示
      jsxs('div', { className: 'inline-flex items-center', style: hasFilters()
        ? { minHeight: '30px', padding: '3px 4px 3px 6px', background: '#fff', border: '1px solid ' + LINE2, borderRadius: 99, gap: '4px', overflow: 'hidden' }
        : { minHeight: '30px', padding: '3px 14px', border: '1px dashed ' + LINE2, borderRadius: 99, fontSize: '0.6875rem', color: FAINT }, children: [
        hasFilters() ? defs.map(function(f) {
          var sel = filters[f.k] || []
          if (!sel.length) return null
          return jsxs('span', { key: f.k, className: 'inline-flex items-center shrink-0', style: { gap: '4px', height: '22px', padding: '0 4px 0 8px', borderRadius: 99, fontSize: '0.75rem', whiteSpace: 'nowrap' }, children: [
            jsx('span', { style: { color: MUT }, children: f.label }),
            jsx('span', { style: { color: INK, fontWeight: 500 }, children: sel.map(function(v) { return iwOptLabel(f.k, v) }).join('、') }),
            jsx('span', { title: '移除该条件', onClick: function() { clearField(f.k) }, className: 'cursor-pointer select-none pw-hover-faint', style: { width: '14px', height: '14px', lineHeight: '14px', borderRadius: 99, textAlign: 'center', color: FAINT, fontSize: '0.6875rem' }, children: '✕' }),
          ] }, f.k)
        }) : jsx('span', { children: '暂无筛选条件' }),
        hasFilters() ? jsx('span', { title: '添加筛选', onClick: function() { setMenuOpen(!menuOpen); setOpenSub(null) }, className: 'cursor-pointer select-none inline-flex items-center justify-center shrink-0 pw-hover-faint', style: { width: '20px', height: '20px', borderRadius: 99, color: MUT, fontSize: '0.875rem', lineHeight: 1 }, children: '+' }) : null,
        // Clear 作为 bullet 内最后一个胶囊 button（仅有筛选条件时渲染）
        hasFilters() ? jsx('span', { onClick: clearAllFilters, className: 'cursor-pointer select-none inline-flex items-center shrink-0 pw-hover-faint', style: { height: '22px', lineHeight: '22px', padding: '0 8px', borderRadius: 99, fontSize: '0.6875rem', color: MUT, whiteSpace: 'nowrap' }, children: 'Clear' }) : null,
      ]}),
      jsx('span', { className: 'flex-1' }),
      // 圆按钮原语：筛选菜单 + 视图切换（图标显示当前视图，点击切换）；筛选菜单锚定到按钮容器（非筛选行）
      jsxs('div', { style: { position: 'relative', display: 'flex', alignItems: 'center', gap: '8px' }, children: [
      jsx(RoundBtn, { title: '筛选', rkey: 'iw-filter', active: menuOpen, onClick: function() { setMenuOpen(!menuOpen); setOpenSub(null) }, children: jsx(Codicon, { name: 'filter', className: 'text-[0.875rem]' }) }),
      jsx(RoundBtn, { title: view === 'board' ? '当前：看板，点击切换 List' : '当前：List，点击切换看板', rkey: 'iw-view', onClick: function() { setView(view === 'board' ? 'list' : 'board') }, children: jsx(Codicon, { name: view === 'board' ? 'pw-board' : 'pw-list', className: 'text-[0.875rem]' }) }),
      // 筛选菜单弹层：锚定漏斗按钮右对齐展开；一级字段 → hover 展开二级可选值（多选，勾选即时生效）
      menuOpen && jsxs(Fragment, { children: [
        jsx('div', { style: { position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 40 }, onClick: function() { setMenuOpen(false); setOpenSub(null) } }),
        jsx('div', { style: { position: 'absolute', top: '100%', right: 0, zIndex: 50, marginTop: '6px', background: '#fff', border: '1px solid ' + LINE2, borderRadius: '12px', boxShadow: SH_RAISED, padding: '5px', minWidth: '170px' }, onMouseLeave: function() { setOpenSub(null) }, children:
          defs.map(function(f) {
            var sel = filters[f.k] || []
            return jsxs('div', { key: f.k, style: { position: 'relative' }, onMouseEnter: function() { setOpenSub(f.k) }, children: [
              jsxs('div', { className: 'flex items-center gap-2 cursor-pointer select-none', style: { padding: '6px 10px', borderRadius: '7px', fontSize: '0.8125rem', color: INK, whiteSpace: 'nowrap', background: openSub === f.k ? HOV : 'transparent' }, children: [
                jsx('span', { children: f.label }),
                sel.length ? jsx('span', { style: { marginLeft: 'auto', fontSize: '0.6875rem', color: FAINT }, children: sel.length }) : null,
                jsx('span', { style: { marginLeft: sel.length ? '6px' : 'auto', color: FAINT, fontSize: '0.75rem' }, children: '›' }),
              ] }),
              openSub === f.k && jsx('div', { style: { position: 'absolute', right: '100%', top: '-5px', marginRight: '2px', background: '#fff', border: '1px solid ' + LINE2, borderRadius: '12px', boxShadow: SH_RAISED, padding: '5px', minWidth: '150px', maxHeight: '260px', overflowY: 'auto' }, children:
                f.opts.map(function(o) {
                  var on = sel.indexOf(o.v) >= 0
                  return jsxs('div', { key: o.v, onClick: function() { toggleFilter(f.k, o.v) }, className: 'flex items-center gap-2 cursor-pointer select-none', style: { padding: '6px 10px', borderRadius: '7px', fontSize: '0.8125rem', whiteSpace: 'nowrap', color: on ? ACC : INK, fontWeight: on ? 500 : 400 }, children: [
                    jsx('span', { style: { width: '14px', height: '14px', border: '1px solid ' + IN_BRD, borderRadius: '4px', background: on ? ACC : '#fff', color: '#fff', fontSize: '0.5625rem', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }, children: on ? '✓' : '' }),
                    o.dot ? dot(o.dot, 7) : null,
                    jsx('span', { children: o.label }),
                  ] })
                }) }),
            ] })
          })
        }),
      ] }),
      ]}),
    ]}),
    // 内容区：List / 看板
    R.loading ? jsx(Center, { icon: 'loading', spin: true, text: '加载中…' })
    : view === 'list'
      ? listView()
      : filtered.length === 0 ? jsx(Center, { icon: 'tasklist', text: 'No issues match the filter' })
      : boardView(),
  ]})
}

// ─── Project Detail（三模块：项目信息 / 当前任务 / 项目会话）──
function ProjectDetail(R) {
  var today = todayLocal()
  var pjn = R.pj(R.sel), p_ts = R.pts(R.sel)
  var sm = useState(false), sessAll = sm[0], setSessAll = sm[1]
  var done = p_ts.filter(function(x) { return x.status === 'Done' || x.status === 'Dropped' }).length
  var sessShown = sessAll ? R.sess : R.sess.slice(0, 6)

  // 模块标题
  function ModHead(props) {
    return jsxs('div', { className: 'flex items-center', style: { marginBottom: '6px' }, children: [
      jsx('span', { className: 'text-[0.9375rem] font-semibold', style: { color: INK, lineHeight: '24px' }, children: props.title }),
      props.count !== undefined && jsx('span', { className: 'ml-1.5 text-[0.6875rem]', style: { color: MUT, lineHeight: '24px' }, children: props.count }),
      jsx('span', { className: 'flex-1' }),
      props.action && jsx(Btn, { onClick: props.onAction, children: props.action }),
    ]})
  }

  return jsxs(Fragment, { children: [
    jsx('div', { 'data-pw': '1', className: S.page, style: { background: PAGE }, children: jsxs('div', { className: S.wrap, children: [
      // Header（Sidebar Nav workspace 头风格）
      jsxs('div', { style: { marginBottom: '15px' }, children: [
        jsx('span', {
          className: 'inline-flex items-center gap-1 text-[0.8125rem] cursor-pointer mb-3 transition-colors',
          style: { color: MUT },
          onClick: function() { R.setSel(null); host.navigate('/projects') },
          children: '← Projects',
        }),
        jsxs('div', { className: 'flex items-center gap-3', children: [
          // 项目字母徽章（Sidebar Nav 品牌徽章风格）
          jsx('span', { className: 'flex items-center justify-center rounded-[8px]', style: { width: '36px', height: '36px', background: ACCS, color: ACC, fontSize: '0.9375rem', fontWeight: 600, flexShrink: 0 }, children: (pjn ? pjn.title : R.sel || '?').charAt(0) }),
          jsxs('div', { className: 'flex-1 min-w-0', children: [
            jsxs('div', { className: 'flex items-center gap-2', children: [
              jsx('span', { className: 'text-[1.0625rem] font-semibold truncate', style: { color: INK, lineHeight: '22px' }, children: pjn ? pjn.title : R.sel }),
              // Finder 打开按钮
              pjn && jsx('span', {
                className: 'flex items-center justify-center w-6 h-6 rounded-md cursor-pointer transition-colors hover:bg-[#f7f8f9]',
                style: { color: MUT },
                title: '在 Finder 中打开',
                onClick: function(e) { e.stopPropagation(); sh('open "' + VAULT + '/' + PROOT + '/' + (pjn.dir || pjn.title) + '"').catch(function(e) { console.error('[pw] Finder open failed:', e) }) },
                children: jsx(Codicon, { name: 'folder-opened', className: 'text-[0.875rem]' }),
              }),
              pjn && jsx('select', {
                className: 'bg-transparent text-[0.6875rem] font-medium border-none outline-none cursor-pointer',
                style: { color: MUT },
                value: pjn.status,
                onChange: function(e) { R.doSetProjField(pjn, 'status', e.target.value) },
                children: [['open','待办'],['In-Progress','进行中'],['Waiting','等待中'],['Routine','常态化'],['Done','已完成'],['Dropped','已取消']].map(function(o) { return jsx('option', { value: o[0], children: o[1] }, o[0]) }),
              }),
            ]}),
            pjn && jsxs('div', { className: 'flex items-center gap-2 text-[0.6875rem] mt-0.5', style: { color: MUT }, children: [
              jsx('input', { type: 'date', defaultValue: pjn.start || '', style: { color: MUT, border: 'none', background: 'transparent', outline: 'none', fontSize: '0.6875rem', cursor: 'pointer' }, onChange: function(e) { R.doSetProjField(pjn, 'start', e.target.value) } }),
              jsx('span', { children: '→' }),
              jsx('input', { type: 'date', defaultValue: pjn.due || '', style: { color: MUT, border: 'none', background: 'transparent', outline: 'none', fontSize: '0.6875rem', cursor: 'pointer' }, onChange: function(e) { R.doSetProjField(pjn, 'due', e.target.value) } }),
              jsx('span', { children: '· ' + done + '/' + p_ts.length + ' 任务完成' }),
            ]}),
          ]}),
        ]}),
      ]}),

      pjn && jsxs('div', { style: { marginTop: '15px' }, children: [
        jsx(ModHead, { title: '项目信息' }),
        jsxs('div', { style: { display: 'flex', flexDirection: 'column', gap: '8px' }, children: [
          // 卡片1：项目背景（Context Cards chunk，全部内联 style）
          jsxs('div', { style: { overflow: 'hidden', borderRadius: '10px', background: SURF, boxShadow: SH_CARD }, children: [
            // 卡片头：icon + 标题 + 最右侧编辑（10px 12px）
            jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 12px', borderBottom: '1px solid ' + LINE }, children: [
              jsx(Codicon, { name: 'book', style: { color: MUT, fontSize: '12px' } }),
              jsx('span', { style: { flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '13px', fontWeight: 500, color: INK }, children: '项目背景' }),
              jsx('span', { className: 'pw-hover-acc', style: { fontSize: '11px', color: FAINT, cursor: 'pointer', flexShrink: 0, transition: 'color 150ms' }, onClick: function() { R.setEf('bg') }, children: '编辑' }),
            ]}),
            R.ef === 'bg'
              ? jsxs('div', { style: { padding: '12px 12px 12px 12px' }, children: [
                  jsx(Input, { as: 'textarea', id: 'editInput', defaultValue: pjn.background || '', autoFocus: true, border: LINE2, minHeight: '88px' }),
                  jsxs('div', { style: { display: 'flex', gap: '8px', marginTop: '8px' }, children: [
                    jsx(Btn, { onClick: R.doSaveOv, children: '保存' }),
                    jsx('span', { className: 'inline-flex items-center text-[0.6875rem] px-2.5 cursor-pointer select-none transition-colors hover:bg-[#f4f5f6] border border-[#e5e5e5]', style: { color: BODY, borderRadius: '8px', height: '24px', lineHeight: '24px' }, onClick: function() { R.setEf(null) }, children: '取消' }),
                  ]}),
                ]})
              : jsx('p', { style: { margin: '0', padding: '12px 12px 12px 12px', fontSize: '12.5px', lineHeight: '1.625', color: BODY, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }, children: pjn.background || '暂无背景说明' }),
          ]}),
          // 卡片2：项目目标（Context Cards chunk，全部内联 style）
          jsxs('div', { style: { overflow: 'hidden', borderRadius: '10px', background: SURF, boxShadow: SH_CARD }, children: [
            // 卡片头：icon + 标题 + 最右侧编辑（10px 12px）
            jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 12px', borderBottom: '1px solid ' + LINE }, children: [
              jsx(Codicon, { name: 'target', style: { color: MUT, fontSize: '12px' } }),
              jsx('span', { style: { flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '13px', fontWeight: 500, color: INK }, children: '项目目标' }),
              jsx('span', { className: 'pw-hover-acc', style: { fontSize: '11px', color: FAINT, cursor: 'pointer', flexShrink: 0, transition: 'color 150ms' }, onClick: function() { R.setEf('goal') }, children: '编辑' }),
            ]}),
            R.ef === 'goal'
              ? jsxs('div', { style: { padding: '12px 12px 12px 12px' }, children: [
                  jsx(Input, { as: 'textarea', id: 'editInput', defaultValue: pjn.goal || '', autoFocus: true, border: LINE2, minHeight: '88px' }),
                  jsxs('div', { style: { display: 'flex', gap: '8px', marginTop: '8px' }, children: [
                    jsx(Btn, { onClick: R.doSaveOv, children: '保存' }),
                    jsx('span', { className: 'inline-flex items-center text-[0.6875rem] px-2.5 cursor-pointer select-none transition-colors hover:bg-[#f4f5f6] border border-[#e5e5e5]', style: { color: BODY, borderRadius: '8px', height: '24px', lineHeight: '24px' }, onClick: function() { R.setEf(null) }, children: '取消' }),
                  ]}),
                ]})
              : jsx('p', { style: { margin: '0', padding: '12px 12px 12px 12px', fontSize: '12.5px', lineHeight: '1.625', color: BODY, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }, children: pjn.goal || '暂无目标说明' }),
          ]}),
        ]}),
      ]}),

      // ── 模块 2：当前任务（看板布局） ──
      jsxs('div', { style: { marginTop: '20px' }, children: [
        jsx(ModHead, { title: 'Issues', count: done + '/' + p_ts.length + ' 完成', action: '+ New Issue', onAction: function() { R.setMd('task') } }),
        jsx('div', { className: 'flex gap-3 overflow-x-auto', style: { paddingBottom: '14px' }, children: BOARD_GROUPS.map(function(g) {
            var gt = p_ts.filter(function(x) { return (g.match || [g.status]).indexOf(x.status) >= 0 })
            return jsx(BoardColumn, { key: g.status, g: g, tasks: gt, R: R, today: today, variant: 'project', dropSource: p_ts })
          }) }),
      ]}),

      // ── 模块 3：项目会话 ──
      jsxs('div', { style: { marginTop: '20px' }, children: [
        jsxs('div', { className: 'flex items-center', style: { marginBottom: '6px' }, children: [
          jsx('span', { className: 'text-[0.9375rem] font-semibold', style: { color: INK, lineHeight: '24px' }, children: 'Sessions' }),
          jsxs('span', { className: 'text-[0.6875rem] ml-2', style: { color: MUT, lineHeight: '24px' }, children: [R.sess.length, ' 个'] }),
          jsx('span', { className: 'flex-1' }),
          jsx(Btn, { onClick: function() { if (pjn) R.doCreateSess(pjn) }, children: '+ 新会话' }),
        ]}),
        R.sess.length === 0
          ? jsx('div', { className: 'overflow-hidden rounded-[10px] bg-surface', style: { boxShadow: SH_CARD, borderRadius: '10px', background: SURF, overflow: 'hidden' }, children: jsx('div', { style: { minWidth: '420px' }, children: [
              // 表头（Filter Table）
              jsxs('div', { className: 'flex items-center gap-3 px-3 py-2 text-[0.6875rem] font-medium uppercase tracking-wide', style: { color: MUT, borderBottom: '1px solid ' + LINE, display: 'flex', alignItems: 'center', gap: '12px', padding: '8px 12px', fontSize: '11px', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.025em' }, children: [
                jsx('span', { className: 'flex-1', style: { flex: 1 }, children: '会话标题' }),
                jsx('span', { className: 'w-24 shrink-0', style: { width: '96px', flexShrink: 0 }, children: '来源' }),
                jsx('span', { className: 'w-28 shrink-0', style: { width: '112px', flexShrink: 0 }, children: '最后活动' }),
                jsx('span', { className: 'w-16 shrink-0 text-right', style: { width: '64px', flexShrink: 0, textAlign: 'right' }, children: '操作' }),
              ]}),
              // 空提示行
              jsx('div', { style: { padding: '28px 12px', textAlign: 'center', fontSize: '12px', color: MUT }, children: '暂无关联会话，点击右上角「+ 新会话」创建' }),
            ]}) })
          : jsxs(Fragment, { children: [
              // Filter Table 容器（全部内联 style，避免 Tailwind JIT 不可靠）
              jsx('div', { className: 'overflow-hidden rounded-[10px] bg-surface', style: { boxShadow: SH_CARD, borderRadius: '10px', background: SURF, overflow: 'hidden' }, children: jsxs('div', { className: 'min-w-[420px]', style: { minWidth: '420px' }, children: [
                // 表头（Filter Table）
                jsxs('div', { className: 'flex items-center gap-3 px-3 py-2 text-[0.6875rem] font-medium uppercase tracking-wide', style: { color: MUT, borderBottom: '1px solid ' + LINE, display: 'flex', alignItems: 'center', gap: '12px', padding: '8px 12px', fontSize: '11px', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.025em' }, children: [
                  jsx('span', { className: 'flex-1', style: { flex: 1 }, children: '会话标题' }),
                  jsx('span', { className: 'w-24 shrink-0', style: { width: '96px', flexShrink: 0 }, children: '来源' }),
                  jsx('span', { className: 'w-28 shrink-0', style: { width: '112px', flexShrink: 0 }, children: '最后活动' }),
                  jsx('span', { className: 'w-16 shrink-0 text-right', style: { width: '64px', flexShrink: 0, textAlign: 'right' }, children: '操作' }),
                ]}),
                sessShown.map(function(s) {
                  var lastTime = s.last_activity_at ? new Date(s.last_activity_at * 1000).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'
                  var src = s.source || ''
                  var bg = INSET, fg = BODY
                  if (src === 'kanban') { bg = PURPLE_T; fg = PURPLE }
                  else if (src === 'subagent') { bg = INSET; fg = BODY }
                  else if (src === 'cron') { bg = ORANGE_T; fg = ORANGE }
                  else if (['desktop', 'cli', 'webui', 'tui', 'weixin', 'acp'].indexOf(src) >= 0) { bg = ACCS; fg = ACC }
                  // Filter Table 行：hover 底色用 JS 事件（Tailwind JIT 不可靠）
                  return jsxs('div', {
                    className: 'flex items-center gap-3 px-3 py-2.5 cursor-pointer transition-colors duration-100 pw-hover',
                    style: { display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 12px', cursor: 'pointer', transition: 'background-color 100ms', borderBottom: '1px solid ' + LINE },
                    onClick: function() { host.navigate('/' + encodeURIComponent(s.id)) },
                    children: [
                      // 标题（无徽章，Filter Table 风格）
                      jsx('span', { className: 'flex-1 min-w-0 text-[0.8125rem] font-medium truncate', style: { flex: 1, minWidth: 0, fontSize: '13px', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: INK }, children: s.title || '(无标题)' }),
                      // 来源（状态chip 风格）
                      jsxs('div', { className: 'w-24 shrink-0', style: { width: '96px', flexShrink: 0 }, children: [
                        src ? jsx('span', { className: 'inline-flex h-5 items-center rounded-full px-2 text-[11px] font-medium', style: { display: 'inline-flex', alignItems: 'center', height: '20px', borderRadius: '99px', padding: '0 8px', fontSize: '11px', fontWeight: 500, background: bg, color: fg }, children: src }) : jsx('span', { className: 'text-[0.6875rem]', style: { fontSize: '11px', color: FAINT }, children: '—' }),
                      ]}),
                      // 最后活动
                      jsx('div', { className: 'w-28 shrink-0 text-[0.75rem] tabular-nums truncate', style: { width: '112px', flexShrink: 0, fontSize: '12px', fontVariantNumeric: 'tabular-nums', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: MUT }, children: lastTime }),
                      // 操作（继续）
                      jsx('div', { className: 'w-16 shrink-0 flex justify-end', style: { width: '64px', flexShrink: 0, display: 'flex', justifyContent: 'flex-end' }, children: jsx('span', {
                        className: 'text-[0.75rem] cursor-pointer transition-colors hover:opacity-70',
                        style: { fontSize: '12px', cursor: 'pointer', transition: 'opacity 150ms', color: ACC, fontWeight: 500 },
                        onClick: function(e) { e.stopPropagation(); host.navigate('/' + encodeURIComponent(s.id)) },
                        children: '继续 →',
                      }) }),
                    ],
                  }, s.id)
                }),
                // 表尾统计（Filter Table footer）
                jsx('div', { className: 'px-3 py-2 text-[0.6875rem]', style: { color: FAINT }, children: [R.sess.length, ' 个会话 · ', (function() { var c = 0; R.sess.forEach(function(x) { if (x.message_count) c += x.message_count }); return c })(), ' 轮对话' ]}),
              ]}) }),
              R.sess.length > 6 && jsx('div', {
                className: 'mt-2 text-center text-[0.8125rem] font-medium py-2 rounded-lg cursor-pointer transition-colors hover:bg-[#f4f5f6]',
                style: { color: ACC },
                onClick: function() { setSessAll(!sessAll) },
                children: sessAll ? '收起' : '加载更多（还有 ' + (R.sess.length - 6) + ' 条）',
              }),
            ] }),
      ]}),
    ]}) }),
    jsx(Modal, R),
    jsx(Toast, R),
  ]})
}

// ─── Inbox 卡片列表（独立视图 /inbox；embedded 时嵌入 chat 分页容器）──────────────
function InboxList(R) {
  var iv = useState([]), items = iv[0], setItems = iv[1]
  // 收集卡片（embedded / 独立两分支共用唯一实现）
  function inboxCard(it) {
    var tsTxt = it.ts || ''
    var d = tsTxt ? tsTxt.slice(0, 10) : ''
    var t2 = tsTxt.length > 11 ? tsTxt.slice(11, 16) : ''
    return jsxs('div', {
      className: 'cursor-pointer transition-all duration-150 pw-hover',
      style: { borderRadius: '10px', padding: '10px 12px', background: '#fff', boxShadow: SH_CARD },
      onClick: function() { R.setSel(it.path); R.setVw('inbox-detail'); R.setDw({ kind: 'inbox', item: it }) },
      children: [
        jsxs('div', { className: 'flex items-center gap-1.5', children: [
          dot(ORANGE, 5),
          jsx('span', { className: 'text-[0.8125rem] font-semibold flex-1 min-w-0 truncate', style: { color: INK }, children: it.title }),
          jsx('span', { style: { color: FAINT }, children: jsx(Codicon, { name: 'chevron-right', className: 'text-[0.75rem]' }) }),
        ]}),
        jsx('div', { className: 'text-[0.625rem] mt-1', style: { color: MUT }, children: (d ? d + (t2 ? ' ' + t2 : '') : '—') }),
        it.first ? jsx('div', { className: 'text-[0.6875rem] mt-1.5', style: { color: BODY, lineHeight: 1.5 }, children: it.first.length > 50 ? it.first.slice(0, 50) + '…' : it.first }) : null,
      ],
    }, it.path)
  }
  var ld2 = useState(true), loading = ld2[0], setLoading = ld2[1]
  function reload() {
    setLoading(true)
    runSpec({ op: 'inbox_list' }).then(function(r) { setItems(r.items || []) }).catch(function(e) { console.error('[pw] inbox_list failed:', e) }).finally(function() { setLoading(false) })
  }
  useEffect(function() { reload() }, [])
  if (R.embedded) {
    // 嵌入 chat 分页容器：去掉 S.page/S.wrap 外壳，内容直接用
    return jsxs(Fragment, { children: [
      jsx('div', { style: { maxWidth: '720px', margin: '0 auto', paddingTop: '56px' }, children: [
        jsxs('div', { className: 'flex items-end justify-between', style: { marginBottom: '28px' }, children: [
          jsxs('div', { children: [
            jsx('div', { className: 'flex items-center gap-3 mt-1', children: [
              jsx('span', { className: S.h1, style: { color: INK }, children: 'Inbox' }),
              jsx('span', { className: S.mut, style: { color: MUT }, children: items.length + ' 条' }),
            ]}),
          ]}),
          jsx(Btn, { onClick: function() { R.setMd('inbox') }, children: '+ New Inbox' }),
        ]}),
        loading ? jsx(Center, { icon: 'loading', spin: true, text: '加载中…' })
          : items.length === 0 ? jsx(Center, { icon: 'inbox', text: '暂无收集，点击右上角灯泡添加' })
          : jsx('div', { className: 'grid gap-2.5', style: { gridTemplateColumns: 'repeat(3, 1fr)' }, children: items.map(inboxCard) }),
      ]}),
    ]})
  }
  return jsxs(Fragment, { children: [
    jsx('div', { 'data-pw': '1', className: S.page, style: { background: PAGE }, children: jsxs('div', { className: S.wrap, children: jsxs('div', { style: { maxWidth: '720px', margin: '0 auto', paddingTop: '24px' }, children: [
      jsxs('div', { className: 'flex items-end justify-between', style: { marginBottom: '28px' }, children: [
        jsxs('div', { children: [
          jsx('span', { className: 'text-[0.8125rem] cursor-pointer transition-colors', style: { color: MUT }, onClick: function() { host.navigate('/agent') }, children: '← 首页' }),
          jsx('div', { className: 'flex items-center gap-3 mt-1', children: [
            jsx('span', { className: S.h1, style: { color: INK }, children: 'Inbox' }),
            jsx('span', { className: S.mut, style: { color: MUT }, children: items.length + ' 条' }),
          ]}),
        ]}),
        jsx(Btn, { onClick: function() { R.setMd('inbox') }, children: '+ New Inbox' }),
      ]}),
      loading ? jsx(Center, { icon: 'loading', spin: true, text: '加载中…' })
        : items.length === 0 ? jsx(Center, { icon: 'inbox', text: '暂无收集，点击右上角灯泡添加' })
        : jsx('div', { className: 'grid gap-2.5', style: { gridTemplateColumns: 'repeat(3, 1fr)' }, children: items.map(inboxCard) })
    ]}) }) }),    jsx(Modal, R),
    jsx(Toast, R),
  ]})
}

// ─── Inbox 详情（查看 + 去处理 → 新 session）──────────
function InboxDetail(R) {
  var dwObj = R.dw || {}
  var item = dwObj.item || dwObj || {}
  var cst = useState(''), content = cst[0], setContent = cst[1]
  useEffect(function() {
    if (item && item.path) {
      runSpec({ op: 'read', path: item.path }).then(function(r) {
        setContent((r && r.content) || '')
      }).catch(function(e) { console.error('[pw] inbox read failed:', e) })
    }
  }, [item && item.path])
  function goHandle() {
    // 回到 chat 首页 + 输入框内 @ 该文件（作为 inbox chip 预载），不开新 session
    var title = item.title || 'Inbox'
    // 通过全局标记传递预载上下文：ChatHome 挂载时读取并 addCtx
    window.__pwPreloadCtx = { type: 'inbox', name: title, dir: '', path: item.path, inbox_ts: item.ts }
    window.__pwGoChat = true
    R.setSel(null)
    R.setDw(null)
    host.navigate('/agent')
    R.tost('已带回 chat，可继续输入或发送')
  }
  function doDelete() {
    // 先弹出确认（Modal inbox-del 分支），确认后才真正删除
    R.setMd('inbox-del')
  }
  return jsxs(Fragment, { children: [
    jsx('div', { 'data-pw': '1', className: S.page, style: { background: PAGE }, children: jsxs('div', { className: S.wrap, children: jsxs('div', { style: { maxWidth: '720px', margin: '0 auto', paddingTop: '24px' }, children: [
      jsxs('div', { className: 'flex items-baseline gap-3 mb-6', children: [
        jsx('span', { className: 'text-[0.8125rem] cursor-pointer transition-colors', style: { color: MUT }, onClick: function() { R.setVw('inbox') }, children: '← Inbox' }),
        jsx('span', { className: S.h1, style: { color: INK }, children: item.title || 'Inbox 收集' }),
      ]}),
      jsxs('div', { className: 'overflow-hidden rounded-[10px] bg-surface', style: { boxShadow: SH_CARD }, children: [
        jsxs('div', { className: 'flex items-center justify-between px-4 py-3', style: { borderBottom: '1px solid ' + LINE }, children: [
          jsx('span', { className: 'text-[0.6875rem]', style: { color: FAINT }, children: (item.ts || '').slice(0, 10) }),
          jsxs('div', { className: 'flex items-center gap-2', children: [
            jsx('span', { className: 'inline-flex items-center text-[0.6875rem] font-medium px-2.5 cursor-pointer select-none transition-colors hover:bg-[#f4f5f6] border border-[#e5e5e5]', style: { color: DANGER, borderRadius: '8px', height: '24px', lineHeight: '24px' }, onClick: doDelete, children: '删除' }),
            jsx(Btn, { onClick: goHandle, children: '去处理 →' }),
          ]}),
        ]}),
        jsx('div', { className: 'px-4 py-3 text-[0.8125rem] whitespace-pre-wrap', style: { color: BODY, minHeight: '120px' }, children: content || item.body || item.first || '（空）' }),
      ]}),
    ]}) }) }),
    jsx(Modal, R),
    jsx(Toast, R),
  ]})
}

// ─── Prop Row (项目/任务属性行：状态/日期，可内联编辑) ─────
function PropRow(props) {
  var st = useState(false), editing = st[0], setEditing = st[1]
  var labelMap = {
    open: '待办', 'In-Progress': '进行中', Waiting: '等待中', Done: '已完成', Dropped: '已取消',
    p0: 'P0', p1: 'P1', p2: 'P2',
  }
  var displayVal = labelMap[props.value] || props.value || '—'
  return jsxs('div', { className: 'px-3.5 py-3' + (props.last ? '' : ' border-b border-[#f7f8f9]'), children: [
    jsxs('div', { className: 'flex items-center', children: [
      jsx('span', { className: 'text-[0.6875rem] font-medium', style: { color: MUT }, children: props.label }),
      jsx('span', { className: 'flex-1' }),
      !editing && jsx('span', {
        className: 'text-[0.625rem] cursor-pointer transition-colors hover:opacity-70',
        style: { color: FAINT },
        onClick: function() { setEditing(true) },
        children: '编辑',
      }),
    ]}),
    editing
      ? jsxs('div', { className: 'mt-2 flex items-center gap-2', children: [
          jsx(Input, { as: props.type === 'select' ? 'select' : 'input', id: 'propInput',
                defaultValue: props.value || '', type: props.type, options: props.options }),
          jsx(Btn, { onClick: function() {
            var v = document.getElementById('propInput').value
            props.onSave(v); setEditing(false)
          }, children: '保存' }),
          jsx('span', { className: 'inline-flex items-center text-[0.6875rem] px-2.5 cursor-pointer select-none transition-colors hover:bg-[#f4f5f6] border border-[#e5e5e5]', style: { color: BODY, borderRadius: '8px', height: '24px', lineHeight: '24px' }, onClick: function() { setEditing(false) }, children: '取消' }),
        ]})
      : jsx('div', { className: 'text-[0.75rem] mt-1', style: { color: BODY }, children: displayVal }),
  ]})
}

// ─── Info Row (项目信息卡内的一行：背景/目标) ────────────
function InfoRow(props) {
  return jsxs('div', { className: 'px-3.5 py-3' + (props.last ? '' : ' border-b border-[#ecedef]'), children: [
    jsxs('div', { className: 'flex items-center mb-1.5', children: [
      jsx('span', { className: 'text-[0.6875rem] font-medium uppercase tracking-wide', style: { color: MUT }, children: props.label }),
      jsx('span', {
        className: 'ml-auto text-[0.625rem] cursor-pointer transition-colors hover:opacity-70',
        style: { color: FAINT },
        onClick: props.onEdit,
        children: '编辑',
      }),
    ]}),
    props.editing
      ? jsxs('div', { children: [
          jsx(Input, { as: 'textarea', id: 'editInput', defaultValue: props.text || '', autoFocus: true, minHeight: '88px' }),
          jsxs('div', { className: 'flex gap-2 mt-2', children: [
            jsx(Btn, { onClick: props.onSave, children: '保存' }),
            jsx('span', { className: 'inline-flex items-center text-[0.6875rem] px-2.5 cursor-pointer select-none transition-colors hover:bg-[#f4f5f6] border border-[#e5e5e5]', style: { color: BODY, borderRadius: '8px', height: '24px', lineHeight: '24px' }, onClick: props.onCancel, children: '取消' }),
          ]}),
        ]})
      : jsx('div', { className: 'text-[0.75rem] leading-[1.7]', style: { color: BODY, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }, children: props.text || '—' }),
  ]})
}

// ─── Task Detail Page（独立页面）───────────────
function TaskDetailPage(R) {
  var t = R.dw
  if (!t || t.kind === 'inbox') return null
  var today = todayLocal()

  // ── state ──
  var tdF = useState(false), tdEditing = tdF[0], setTdEditing = tdF[1]
  var etF = useState(false), editingTitle = etF[0], setEditingTitle = etF[1]
  var leF = useState(-1), logEdit = leF[0], setLogEdit = leF[1]
  var fs = useState(0), force = fs[0], setForce = fs[1]
  var detailExpanded = useState(false), isDetailExpanded = detailExpanded[0], setDetailExpanded = detailExpanded[1]
  var hm = useState(false), handleMenuOpen = hm[0], setHandleMenuOpen = hm[1]
  var tlData = useState(null), timeline = tlData[0], setTimeline = tlData[1] // 保留 state 避免 hooks 顺序变化（已不使用）
  var tlLoaded = useState(false), sessTlLoaded = tlLoaded[0], setSessTlLoaded = tlLoaded[1]
  var taskSess = useState([]), sessList = taskSess[0], setSessList = taskSess[1]

  // ── data loading ──
  useEffect(function() {
    if (!t.path) return
    // 加载 session 列表（去处理下拉用）
    var ids = (t.session_ids || '').split(',').filter(Boolean)
    if (ids.length) {
      runSpec({ op: 'ops_session_by_ids', ids: ids.join(',') }).then(function(r) {
        setSessList(r.sessions || [])
      }).catch(function(e) { console.error('[pw] loadTaskSess failed:', e) })
      setSessTlLoaded(true)
    } else {
      setSessTlLoaded(true)
    }
  }, [t.path, t.session_ids])

  // ── helpers ──
  function saveTd() {
    var v = document.getElementById('tdInput').value || ''
    setForce(force + 1); setTdEditing(false)
    R.updateSection(t.path, '任务详情', v).catch(function(e) { console.error('[pw] updateSection failed:', e); R.load() })
  }
  function saveLogEdit(i) {
    var inp = document.getElementById('logEditInput' + i)
    if (!inp) { setLogEdit(-1); return }
    var v = inp.value.trim()
    if (v) { setForce(force + 1); editLog(t.path, i, v).catch(function(e) { console.error('[pw] editLog failed:', e); R.load() }) }
    setLogEdit(-1)
  }
  function doReviewResumeSess(sid) {
    host.request('session.resume', { session_id: sid }).then(function() {
      host.navigate('/' + encodeURIComponent(sid))
    }).catch(function(e) { R.tost('恢复失败：' + ((e && e.message) || '未知错误')) })
  }
  function doNewSession() {
    setHandleMenuOpen(false)
    R.doCreateSess(R.pj(t.project || t.dir), t)
  }
  function doGoProject() {
    var pjn = R.pj(t.project || t.dir)
    if (pjn) { R.setSel(pjn.title); R.setVw('project'); R.loadSessions(pjn.dir || pjn.title).then(R.setSess) }
  }

  // ── 验收标准 ──
  var acLen = (t.acceptance_criteria || []).length
  var acDone = (t.acceptance_criteria || []).filter(function(a) { return typeof a === 'object' ? !!a.done : false }).length
  var acItems = (t.acceptance_criteria || []).map(function(a, i) {
    var d = typeof a === 'object' ? a.done : false, fl = typeof a === 'object' ? a.failed : false, txt = typeof a === 'object' ? a.text : a
    function doToggle() {
      var na = typeof a === 'object' ? Object.assign({}, a) : { text: String(a), done: false, failed: false }
      if (d) { na.done = false; na.failed = true }
      else if (fl) { na.done = false; na.failed = false }
      else { na.done = true; na.failed = false }
      try { if (t.acceptance_criteria) t.acceptance_criteria[i] = na } catch(e) {}
      setForce(force + 1)
      R.toggleAc(t.path, i).catch(function(e) { console.error('[pw] toggleAc failed:', e); R.load() })
    }
    var mkBg = d ? GREEN : fl ? RED : 'transparent'
    var mkBd = d ? GREEN : fl ? RED : LINE2
    var mkFg = d ? '#fff' : fl ? '#fff' : 'transparent'
    return jsxs('div', {
      className: 'flex items-center gap-2 px-2.5 py-1 pw-hover',
      style: { borderBottom: i === acLen - 1 ? 'none' : '1px solid ' + LINE, fontSize: '11px' },
      children: [
        jsx('span', {
          className: 'shrink-0 cursor-pointer select-none flex items-center justify-center transition-all duration-200',
          style: { width: 13, height: 13, borderRadius: 99, border: '1.5px solid ' + mkBd, background: mkBg, color: mkFg, fontSize: '8px', lineHeight: '1', fontWeight: 700 },
          onClick: doToggle,
          children: d ? '✓' : fl ? '✕' : '',
        }),
        jsx('span', { style: { flex: 1, minWidth: 0, color: fl ? DANGER : d ? MUT : BODY, textDecoration: d ? 'line-through' : 'none', transition: 'color .2s' }, children: txt }),
      ],
    }, i)
  })

  // ── 统一时间线：YAML 推进记录（含人工/review/kanban），按时间倒序 ──
  var tlEntries = []
  // 人工记录（旧格式，仅当无 YAML 条目时显示——避免新旧格式混排）
  if (!t.logs_yaml || !t.logs_yaml.trim()) {
    ;(t.logs || []).forEach(function(l, i) {
      var dateStr = l.date || ''
      var day = dateStr.length >= 10 ? dateStr.slice(0, 10) : (dateStr.length >= 5 ? new Date().getFullYear() + '-' + dateStr.slice(0, 5) : '')
      tlEntries.push({ type: 'log', date: day, raw_date: dateStr, text: l.text, idx: i })
    })
  }
  // YAML 推进记录（新 schema）
  if (t.logs_yaml) {
    // 简单 YAML 解析：按 - date: 分割条目
    var yamlEntries = t.logs_yaml.split(/\n(?=- date:)/)
    yamlEntries.forEach(function(block) {
      if (!block.trim()) return
      var entry = { type: 'yaml', date: '', raw_date: '', summary: '', logType: '', sessions: [], outputs: [], decisions: [], risks: [], pending: [] }
      var lines = block.split('\n')
      var curField = '', curSub = null
      lines.forEach(function(line) {
        var m
        if (m = line.match(/^-\s+date:\s*(.+)/)) { entry.date = m[1].trim(); entry.raw_date = m[1].trim(); curField = '' }
        else if (m = line.match(/^\s+type:\s*(.+)/)) { entry.logType = m[1].trim(); curField = '' }
        else if (m = line.match(/^\s+summary:\s*(.+)/)) { entry.summary = m[1].trim(); curField = '' }
        else if (line.match(/^\s+sessions:/)) { curField = 'sessions'; curSub = null }
        else if (line.match(/^\s+outputs:/) || line.match(/^\s+deliverables:/)) { curField = 'outputs' }
        else if (line.match(/^\s+decisions:/)) { curField = 'decisions'; curSub = null }
        else if (line.match(/^\s+risks:/)) { curField = 'risks' }
        else if (line.match(/^\s+pending:/)) { curField = 'pending' }
        else if (curField === 'sessions' && (m = line.match(/^\s+-\s+id:\s*(.+)/))) { curSub = { id: m[1].trim(), source: '' }; entry.sessions.push(curSub) }
        else if (curField === 'sessions' && curSub && (m = line.match(/^\s+source:\s*(.+)/))) { curSub.source = m[1].trim() }
        else if (curField === 'outputs' && (m = line.match(/^\s+-\s+(.+)/))) { entry.outputs.push(m[1].trim()) }
        else if (curField === 'decisions' && (m = line.match(/^\s+-\s+desc:\s*(.+)/))) { curSub = { desc: m[1].trim(), by: '' }; entry.decisions.push(curSub) }
        else if (curField === 'decisions' && curSub && (m = line.match(/^\s+by:\s*(.+)/))) { curSub.by = m[1].trim() }
        else if (curField === 'risks' && (m = line.match(/^\s+-\s+(.+)/))) { entry.risks.push(m[1].trim()) }
        else if (curField === 'pending' && (m = line.match(/^\s+-\s+(.+)/))) { entry.pending.push(m[1].trim()) }
      })
      // 日期补全为 YYYY-MM-DD HH:mm:ss（排序用）；raw_date 保留原始格式用于显示
      if (entry.date) {
        if (entry.date.length <= 5) entry.date = new Date().getFullYear() + '-' + entry.date
        // 补全到秒级（无时间部分则补 00:00:00）
        if (entry.date.length === 10) entry.date += ' 00:00:00'
      }
      tlEntries.push(entry)
    })
  }
  // 按日期倒序
  tlEntries.sort(function(a, b) { return (b.date || '').localeCompare(a.date || '') })

  // ── 任务详情截断 ──
  var detailText = t.task_detail || ''
  var detailLines = detailText.split('\n')
  var needClamp = detailLines.length > 3 || detailText.length > 200
  var clampedDetail = needClamp && !isDetailExpanded ? detailLines.slice(0, 3).join('\n') : detailText

  return jsxs(Fragment, { children: [
    jsx('div', { 'data-pw': '1', className: S.page, style: { background: PAGE }, children: jsxs('div', { className: S.wrap, children: [
      // 面包屑
      jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: MUT, marginBottom: '18px' }, children: [
        jsx('span', { style: { cursor: 'pointer', color: MUT }, onClick: function() { R.setDw(null); R.setVw('issues') }, children: '← Issues' }),
        jsx('span', { style: { color: FAINT }, children: '/' }),
        jsx('span', { style: { cursor: 'pointer', color: MUT }, onClick: doGoProject, children: t.project || t.dir || '' }),
        jsx('span', { style: { color: FAINT }, children: '/' }),
        jsx('span', { style: { color: INK, fontWeight: 500 }, children: t.title }),
      ]}),

      jsxs('div', { style: { display: 'flex', gap: '36px', alignItems: 'flex-start' }, children: [
        // ═══ 主栏 ═══
        jsxs('div', { style: { flex: 1, minWidth: 0 }, children: [
          // 标题
          jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }, children: [
            editingTitle
              ? jsx('input', {
                  id: 'edtTitle', defaultValue: t.title, autoFocus: true,
                  style: { flex: 1, minWidth: 0, fontSize: '19px', fontWeight: 600, color: INK, border: '1px solid ' + ACC, borderRadius: '6px', padding: '2px 6px', outline: 'none', background: '#fff', height: '32px', letterSpacing: '-0.01em' },
                  onKeyDown: function(ev) { if (ev.key === 'Enter') { var v = ev.currentTarget.value.trim(); if (v) R.doRenameTitle(t, v); setEditingTitle(false) } if (ev.key === 'Escape') setEditingTitle(false) },
                  onBlur: function(ev) { var v = ev.currentTarget.value.trim(); if (v && v !== t.title) R.doRenameTitle(t, v); setEditingTitle(false) },
                })
              : jsx('span', { style: { flex: 1, minWidth: 0, fontSize: '19px', fontWeight: 600, color: INK, letterSpacing: '-0.01em', lineHeight: 1.3, cursor: 'text' }, onClick: function() { setEditingTitle(true) }, title: '点击编辑标题', children: t.title }),
            t.repeat_mode ? jsx('span', { style: { fontSize: '11px', color: MUT, flexShrink: 0 }, children: '🔁 ' + repLabel(t) }) : null,
            !editingTitle && jsx('span', {
              className: 'pw-hover', style: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: '26px', height: '26px', borderRadius: '5px', cursor: 'pointer', color: MUT, flexShrink: 0 },
              onClick: function() { setEditingTitle(true) }, title: '编辑标题',
              children: '✎',
            }),
          ]}),

          // 任务详情（可折叠）
          jsxs('div', { style: { background: INSET, borderRadius: '5px', marginBottom: '18px', overflow: 'hidden' }, children: [
            jsxs('div', {
              style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', cursor: 'pointer', userSelect: 'none' },
              onClick: function() { if (needClamp) setDetailExpanded(!isDetailExpanded) },
              children: [
                jsx('span', { style: { fontSize: '11px', fontWeight: 500, color: MUT }, children: '任务详情' }),
                jsxs('span', { style: { display: 'flex', alignItems: 'center', gap: '8px' }, children: [
                  !tdEditing && jsx('span', { style: { fontSize: '10px', color: FAINT, cursor: 'pointer' }, onClick: function(ev) { ev.stopPropagation(); setTdEditing(true) }, children: '编辑' }),
                  needClamp && jsx('span', { style: { fontSize: '10px', color: FAINT, transition: 'transform .2s', transform: isDetailExpanded ? 'rotate(90deg)' : 'none' }, children: '▸' }),
                ]}),
              ],
            }),
            tdEditing
              ? jsxs('div', { style: { padding: '0 12px 10px' }, children: [
                  jsx(Input, { as: 'textarea', id: 'tdInput', defaultValue: t.task_detail || '', border: LINE2, minHeight: '200px' }),
                  jsxs('div', { style: { display: 'flex', gap: '6px', marginTop: '6px' }, children: [
                    jsx(Btn, { onClick: saveTd, children: '保存' }),
                    jsx('span', { className: 'pw-hover', style: { display: 'inline-flex', alignItems: 'center', fontSize: '11px', padding: '0 8px', height: '24px', lineHeight: '24px', borderRadius: '5px', cursor: 'pointer', color: BODY }, onClick: function() { setTdEditing(false) }, children: '取消' }),
                  ]}),
                ]})
              : jsxs('div', { style: { padding: '0 12px 10px' }, children: [
                  jsx('div', { style: { fontSize: '12px', lineHeight: 1.7, color: BODY, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }, children: clampedDetail || '—' }),
                  needClamp && jsx('span', {
                    style: { fontSize: '10px', color: ACC, cursor: 'pointer', display: 'inline-block', marginTop: '4px' },
                    onClick: function(ev) { ev.stopPropagation(); setDetailExpanded(!isDetailExpanded) },
                    children: isDetailExpanded ? '收起' : '展开全文',
                  }),
                ]}),
          ]}),

          // 时间线输入（与时间线容器同宽）
          jsxs('div', { style: { display: 'flex', gap: '6px', marginBottom: '14px', width: '100%' }, children: [
            jsx('div', { style: { flex: 1, minWidth: 0 }, children: jsx(Input, { id: 'logInput', placeholder: '添加推进记录…', classNameExtra: ' w-full', onKeyDown: function(ev) { if (ev.key === 'Enter' && !ev.isComposing && ev.keyCode !== 229) R.doAddLog(t) } }) }),
            jsx(Btn, { onClick: function() { R.doAddLog(t) }, children: '添加', variant: 'lg' }),
          ]}),

          // 统一时间线
          jsx('div', { style: { position: 'relative' }, children: [
            jsx('div', { style: { position: 'absolute', left: '5px', top: '8px', bottom: '8px', width: '1px', background: LINE } }),
            tlEntries.length === 0 && sessTlLoaded
              ? jsx('div', { style: { padding: '20px 0', textAlign: 'center', fontSize: '11px', color: FAINT }, children: '暂无推进记录' })
              : tlEntries.map(function(entry, ei) {
                  // YAML 推进记录（新 schema）
                  if (entry.type === 'yaml') {
                    var typeColor = entry.logType === 'kanban' ? PURPLE : entry.logType === 'review' ? ACC : ORANGE
                    var typeBg = entry.logType === 'kanban' ? PURPLE_T : entry.logType === 'review' ? ACCS : ORANGE_T
                    var typeLabel = entry.logType === 'kanban' ? 'kanban' : entry.logType === 'review' ? 'Agent 回顾' : '人工记录'
                    return jsxs('div', { style: { display: 'flex', gap: '12px', padding: '7px 0', position: 'relative' }, children: [
                      jsx('span', { style: { width: '11px', height: '11px', borderRadius: 99, flexShrink: 0, marginTop: '4px', position: 'relative', zIndex: 1, border: '2px solid #fff', background: typeColor } }),
                      jsxs('div', { style: { flex: 1, minWidth: 0 }, children: [
                        jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '3px', flexWrap: 'wrap' }, children: [
                          jsx('span', { style: { fontSize: '10px', color: MUT, fontFamily: 'monospace', flexShrink: 0 }, children: entry.raw_date || entry.date }),
                          jsx('span', { style: { fontSize: '9px', fontWeight: 500, padding: '0 5px', borderRadius: 99, lineHeight: '15px', background: typeBg, color: typeColor, flexShrink: 0 }, children: typeLabel }),
                          // session 跳转链接（普通链接样式，显示 title，靠右）
                          entry.sessions.length > 0 && jsx('span', { style: { marginLeft: 'auto', flexShrink: 0 }, children:
                            entry.sessions.map(function(s) {
                              // 从 sessList 按 ID 查 title（title 可能变，ID 稳定）
                              var sessInfo = sessList.filter(function(x) { return x.id === s.id })[0]
                              var displayTitle = sessInfo ? sessInfo.title : (s.title || s.source || 'session')
                              return jsxs('span', {
                                style: { fontSize: '11px', color: ACC, cursor: 'pointer', flexShrink: 0 },
                                title: '跳转到 session: ' + s.id,
                                onClick: function() { host.navigate('/' + encodeURIComponent(s.id)) },
                                children: ['↗ ', displayTitle],
                              }, s.id)
                            })
                          }),
                        ]}),
                        jsx('div', { style: { fontSize: '12px', color: INK, fontWeight: 500, lineHeight: 1.5, marginBottom: (entry.outputs.length || entry.decisions.length || entry.risks.length || entry.pending.length) ? '4px' : '0' }, children: entry.summary }),
                        (entry.outputs.length > 0 || entry.decisions.length > 0 || entry.risks.length > 0 || entry.pending.length > 0) && jsxs('div', { style: { background: INSET, borderRadius: '5px', padding: '10px 12px', marginTop: '4px' }, children: [
                          entry.outputs.length > 0 && jsxs('div', { style: { marginBottom: '6px' }, children: [
                            jsx('div', { style: { fontSize: '10px', fontWeight: 600, color: GREEN, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '2px' }, children: '产出' }),
                            entry.outputs.map(function(d, di) { return jsx('div', { style: { fontSize: '12px', color: BODY, lineHeight: 1.6, paddingLeft: '8px' }, children: '· ' + d }, 'd' + di) }),
                          ]}),
                          entry.decisions.length > 0 && jsxs('div', { style: { marginBottom: '6px' }, children: [
                            jsx('div', { style: { fontSize: '10px', fontWeight: 600, color: ACC, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '2px' }, children: '关键决策' }),
                            entry.decisions.map(function(d, di) { return jsxs('div', { style: { fontSize: '12px', color: BODY, lineHeight: 1.6, paddingLeft: '8px' }, children: ['· ' + d.desc, d.by === 'ben' ? jsx('span', { style: { fontSize: '10px', color: ACC, marginLeft: '4px' }, children: '(Ben)' }) : null] }, 'dc' + di) }),
                          ]}),
                          entry.risks.length > 0 && jsxs('div', { style: { marginBottom: '6px' }, children: [
                            jsx('div', { style: { fontSize: '10px', fontWeight: 600, color: ORANGE, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '2px' }, children: '⚠ 注意' }),
                            entry.risks.map(function(r, ri) { return jsx('div', { style: { fontSize: '12px', color: BODY, lineHeight: 1.6, paddingLeft: '8px' }, children: '· ' + r }, 'r' + ri) }),
                          ]}),
                          entry.pending.length > 0 && jsxs('div', { children: [
                            jsx('div', { style: { fontSize: '10px', fontWeight: 600, color: MUT, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '2px' }, children: '遗留' }),
                            entry.pending.map(function(p, pi) { return jsx('div', { style: { fontSize: '12px', color: BODY, lineHeight: 1.6, paddingLeft: '8px' }, children: '· ' + p }, 'p' + pi) }),
                          ]}),
                        ]}),
                      ]}),
                    ] }, 'y' + ei)
                  }
                  // 人工记录
                  return jsxs('div', { style: { display: 'flex', gap: '12px', padding: '7px 0', position: 'relative' }, children: [
                    jsx('span', { style: { width: '11px', height: '11px', borderRadius: 99, flexShrink: 0, marginTop: '4px', position: 'relative', zIndex: 1, border: '2px solid #fff', background: LINE2 } }),
                    jsxs('div', { style: { flex: 1, minWidth: 0 }, children: [
                      jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }, children: [
                        jsx('span', { style: { fontSize: '10px', color: MUT, fontFamily: 'monospace', flexShrink: 0 }, children: entry.raw_date || entry.date }),
                        jsx('span', { style: { fontSize: '9px', fontWeight: 500, padding: '0 5px', borderRadius: 99, lineHeight: '15px', background: HOV, color: MUT, flexShrink: 0 }, children: '记录' }),
                      ]}),
                      logEdit === entry.idx
                        ? jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '6px' }, children: [
                            jsx('input', {
                              id: 'logEditInput' + entry.idx, defaultValue: entry.text,
                              style: { flex: 1, color: INK, height: '26px', border: '1px solid ' + IN_BRD, borderRadius: '5px', padding: '0 6px', fontSize: '12px', outline: 'none', minWidth: 0, background: '#fff' },
                              autoFocus: true,
                              onFocus: function(e) { e.target.style.borderColor = FOCUS_BRD },
                              onBlur: function(e) { e.target.style.borderColor = IN_BRD },
                              onKeyDown: function(ev) { if (ev.key === 'Enter') saveLogEdit(entry.idx) },
                            }),
                            jsx('span', { style: { color: ACC, fontSize: '11px', cursor: 'pointer', whiteSpace: 'nowrap' }, onMouseDown: function(e) { e.preventDefault() }, onClick: function() { saveLogEdit(entry.idx) }, children: '保存' }),
                          ] })
                        : jsx('div', {
                            style: { fontSize: '12px', color: BODY, lineHeight: 1.6, cursor: 'text' },
                            title: '双击编辑',
                            onDoubleClick: function() { setLogEdit(entry.idx) },
                            children: entry.text,
                          }),
                    ]}),
                  ] }, 'l' + ei)
                }),
          ]}),
        ]}),

        // ═══ 右栏 ═══
        jsxs('div', { style: { width: '232px', flexShrink: 0, position: 'sticky', top: '28px' }, children: [
          // Review 状态专用按钮组
          t.status === 'Review' && jsxs('div', { style: { marginBottom: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }, children: [
            jsx(Btn, { onClick: function() { R.doReviewPass(t) }, children: [jsx(Codicon, { name: 'check', className: 'text-[0.75rem]' }), ' 验收通过'], gap: true }),
            jsx('span', {
              className: 'pw-hover',
              style: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px', height: '28px', borderRadius: '5px', background: ACC, color: '#fff', fontSize: '11px', fontWeight: 500, cursor: 'pointer', width: '100%' },
              onClick: function() { R.doReviewResume(t) },
              children: '↻ 人为介入处理',
            }),
          ]}),
          // 去处理（顶部）
          jsxs('div', { style: { marginBottom: '16px', position: 'relative' }, children: [
            jsx('button', {
              style: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px', height: '28px', borderRadius: '5px', border: 'none', background: BTN, color: '#fff', fontSize: '11px', fontWeight: 500, cursor: 'pointer', width: '100%' },
              onClick: function() { setHandleMenuOpen(!handleMenuOpen) },
              children: '去处理 ▾',
            }),
            handleMenuOpen && jsxs(Fragment, { children: [
              jsx('div', { style: { position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 40 }, onClick: function() { setHandleMenuOpen(false) } }),
              jsxs('div', { style: { position: 'absolute', top: '100%', left: 0, right: 0, marginTop: '4px', background: '#fff', border: '1px solid ' + LINE2, borderRadius: '8px', boxShadow: '0 4px 16px rgba(0,0,0,0.1)', padding: '4px', zIndex: 50 }, children: [
                jsxs('div', { className: 'pw-hover', style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 8px', borderRadius: '5px', fontSize: '12px', color: INK, cursor: 'pointer' }, onClick: doNewSession, children: [
                  jsx('span', { style: { fontSize: '11px', color: MUT, flexShrink: 0, width: '16px', textAlign: 'center' }, children: '＋' }),
                  jsx('span', { children: 'New Session' }),
                ] }),
                sessList.length > 0 && jsx('div', { style: { height: '1px', background: LINE, margin: '3px 0' } }),
                sessList.length > 0 && jsx('div', { style: { fontSize: '10px', color: FAINT, padding: '4px 8px 2px' }, children: '最近的会话' }),
                sessList.map(function(s) {
                  return jsxs('div', {
                    className: 'pw-hover',
                    style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 8px', borderRadius: '5px', fontSize: '12px', color: INK, cursor: 'pointer' },
                    onClick: function() { setHandleMenuOpen(false); doReviewResumeSess(s.id) },
                    children: [
                      jsx('span', { style: { fontSize: '11px', color: MUT, flexShrink: 0, width: '16px', textAlign: 'center' }, children: '●' }),
                      jsx('span', { style: { flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, children: s.title || '(无标题)' }),
                    ],
                  }, s.id)
                }),
              ] }),
            ] }),
          ]}),

          jsx('div', { style: { height: '1px', background: LINE, margin: '14px 0' } }),

          // 目标与验收
          jsxs('div', { style: { marginBottom: '16px' }, children: [
            jsx('div', { style: { fontSize: '11px', fontWeight: 500, color: FAINT, marginBottom: '6px' }, children: '目标与验收' }),
            jsx('div', { style: { fontSize: '12px', color: BODY, lineHeight: 1.6, marginBottom: '8px' }, children: t.goal || '—' }),
            acItems.length > 0 && jsxs('div', { style: { background: SURF, boxShadow: SH_HAIR, borderRadius: '5px', overflow: 'hidden' }, children: [
              jsxs('div', { style: { padding: '8px 10px', borderBottom: '1px solid ' + LINE }, children: [
                jsxs('div', { style: { display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: '5px' }, children: [
                  jsx('span', { style: { fontSize: '10px', fontWeight: 500, color: BODY }, children: acDone + ' / ' + acLen + ' 条通过' }),
                  jsx('span', { style: { fontSize: '10px', fontWeight: 500, color: acDone === acLen ? GREEN : MUT, fontVariantNumeric: 'tabular-nums' }, children: Math.round(acLen ? acDone / acLen * 100 : 0) + '%' }),
                ]}),
                jsx('div', { style: { height: '3px', borderRadius: '2px', background: FIELD, overflow: 'hidden' }, children: jsx('div', { style: { height: '100%', borderRadius: '2px', background: acDone === acLen ? GREEN : ACC, width: Math.round(acLen ? acDone / acLen * 100 : 0) + '%', transition: 'width 0.3s ease' } }) }),
              ] }),
              acItems,
            ] }),
          ]}),

          jsx('div', { style: { height: '1px', background: LINE, margin: '14px 0' } }),

          // 基础信息
          jsxs('div', { style: { marginBottom: '16px' }, children: [
            jsx('div', { style: { fontSize: '11px', fontWeight: 500, color: FAINT, marginBottom: '6px' }, children: '基础信息' }),
            jsxs('div', { style: { background: INSET, borderRadius: '5px', padding: '10px 12px' }, children: [
              // 状态
              jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 0' }, children: [
                jsx('span', { style: { fontSize: '11px', color: FAINT, width: '40px', flexShrink: 0 }, children: '状态' }),
                dot(SDOT[t.status] || FAINT, 8),
                jsx('select', {
                  style: { fontSize: '12px', color: (SBGC[t.status] || { color: MUT }).color, border: 'none', background: 'transparent', outline: 'none', cursor: 'pointer', padding: 0, height: '20px' },
                  value: t.status,
                  onChange: function(e) { R.doSetField(t, 'status', e.target.value) },
                  children: [['open','待办'],['In-Progress','进行中'],['Waiting','等待中'],['Agent','托管给Agent'],['Review','待人为确认'],['Done','已完成'],['Dropped','已取消']].map(function(o) { return jsx('option', { value: o[0], children: o[1] }, o[0]) }),
                }),
              ] }),
              // 优先级
              jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 0' }, children: [
                jsx('span', { style: { fontSize: '11px', color: FAINT, width: '40px', flexShrink: 0 }, children: '优先级' }),
                buiChip(PBGC[t.priority] ? PBGC[t.priority].color : MUT, PBGC[t.priority] ? PBGC[t.priority].background : HOV, PR[t.priority] || t.priority),
              ] }),
              // 处理人
              jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 0' }, children: [
                jsx('span', { style: { fontSize: '11px', color: FAINT, width: '40px', flexShrink: 0 }, children: '处理人' }),
                jsx(HandlerPicker, { key: 'h' + (t.path || ''), id: 'dwHandler', value: t.handler || '', handlers: R.handlers, plain: true, onSave: function(v) { R.doSetField(t, 'handler', v); t.handler = v } }),
              ] }),
              // 项目
              jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 0' }, children: [
                jsx('span', { style: { fontSize: '11px', color: FAINT, width: '40px', flexShrink: 0 }, children: '项目' }),
                jsx('span', { style: { fontSize: '12px', color: ACC, cursor: 'pointer' }, onClick: doGoProject, children: (t.project || t.dir || '—') + ' →' }),
              ] }),
              // 开始
              jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 0' }, children: [
                jsx('span', { style: { fontSize: '11px', color: FAINT, width: '40px', flexShrink: 0 }, children: '开始' }),
                jsx('input', { type: 'date', defaultValue: t.start || '', style: { fontSize: '12px', color: MUT, border: 'none', background: 'transparent', outline: 'none', cursor: 'pointer', padding: 0 }, onChange: function(e) { R.doSetField(t, 'start', e.target.value) } }),
              ] }),
              // 截止
              jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 0' }, children: [
                jsx('span', { style: { fontSize: '11px', color: FAINT, width: '40px', flexShrink: 0 }, children: '截止' }),
                jsx('input', { type: 'date', defaultValue: t.due || '', style: { fontSize: '12px', color: MUT, border: 'none', background: 'transparent', outline: 'none', cursor: 'pointer', padding: 0 }, onChange: function(e) { R.doSetField(t, 'due', e.target.value) } }),
              ] }),
              // 重复周期（仅有 repeat_mode 的任务显示）
              t.repeat_mode && jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 0' }, children: [
                jsx('span', { style: { fontSize: '11px', color: FAINT, width: '40px', flexShrink: 0 }, children: '循环' }),
                jsx('span', { style: { fontSize: '12px', color: BODY }, children: '🔁 ' + repLabel(t) }),
              ] }),
            ] }),
          ]}),

          jsx('div', { style: { height: '1px', background: LINE, margin: '14px 0' } }),

          // 删除（底部）
          jsx('button', {
            style: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px', height: '28px', borderRadius: '5px', border: 'none', background: RED_T, color: DANGER, fontSize: '11px', fontWeight: 500, cursor: 'pointer', width: '100%' },
            onClick: function() { R.doDeleteTask(t) },
            children: '🗑 删除',
          }),
        ]}),
      ]}),
    ]}) }),
    jsx(Modal, R),
    jsx(Toast, R),
  ] })
}

function Modal(R) {
  if (!R.md) return null

  function modalShell(title, subtitle, bodyChildren, onConfirm, confirmLabel) {
    return jsx('div', {
      className: 'absolute inset-0 z-50 flex items-center justify-center',
      style: { background: 'rgba(23,23,28,0.32)', backdropFilter: 'blur(4px)' },
      onClick: function() { R.setMd(null) },
      children: jsxs('div', {
        className: 'overflow-hidden bg-white flex flex-col',
        style: { width: 560, maxWidth: '94vw', maxHeight: '88vh', borderRadius: '16px', boxShadow: '0 24px 60px rgba(0,0,0,0.16), 0 2px 8px rgba(0,0,0,0.06)' },
        onClick: function(ev) { ev.stopPropagation() },
        children: [
          // Header: 标题左对齐 + 右上角 X
          jsxs('div', { className: 'flex items-center justify-between px-5 pt-4 pb-3.5', style: { borderBottom: '1px solid ' + DIVIDER }, children: [
            jsxs('div', { className: 'flex items-baseline gap-2', children: [
              jsx('h3', { className: 'text-[0.8125rem] font-semibold', style: { color: INK }, children: title }),
              subtitle && jsx('span', { className: 'text-[0.75rem]', style: { color: MUT }, children: subtitle }),
            ]}),
            jsx('span', { className: 'flex items-center justify-center w-6 h-6 rounded-md cursor-pointer transition-colors hover:bg-[#f7f8f9]', style: { color: MUT }, onClick: function() { R.setMd(null) }, children: jsx(Codicon, { name: 'close', className: 'text-[0.875rem]' }) }),
          ]}),
          // Body
          jsx('div', { className: 'flex-1 min-h-0 px-5 py-4 overflow-y-auto', children: bodyChildren }),
          // Footer: 取消(灰边) + 确认(#4a4a4d 深灰)
          jsxs('div', { className: 'flex items-center justify-end gap-2 px-5 py-3', style: { borderTop: '1px solid ' + DIVIDER }, children: [
            jsx('span', {
              className: 'inline-flex items-center text-[0.6875rem] font-medium px-2.5 py-1 cursor-pointer select-none transition-colors hover:bg-[#f4f5f6] border border-[#e5e5e5]',
              style: { color: BODY, borderRadius: '8px' },
              onClick: function() { R.setMd(null) },
              children: '取消',
            }),
            jsx(Btn, { onClick: onConfirm, children: confirmLabel, variant: 'modal' }),
          ]}),
        ],
      }),
    })
  }

  function ModalInput(props) {
    return jsx(Input, { id: props.id, placeholder: props.placeholder, autoFocus: props.autoFocus, type: props.type })
  }
  function ModalTextarea(props) {
    return jsx(Input, { as: 'textarea', id: props.id, placeholder: props.placeholder, minHeight: props.minHeight || '60px' })
  }
  function ModalField(props) {
    return jsxs('div', { style: { marginBottom: '10px' }, children: [
      jsx('label', { className: 'block mb-1 text-[0.6875rem] font-medium', style: { color: '#555' }, children: props.label }),
      props.children,
    ]})
  }

  if (R.md === 'cmd') {
    return modalShell('New Command', null, [
      jsx(ModalField, { key: 'f1', label: '指令标题（文件名）', children: jsx(ModalInput, { id: 'ncName', placeholder: '如：write-weekly-report', autoFocus: true }) }),
      jsx(ModalField, { key: 'f2', label: '指令内容（发送给 Agent 的正文）', children: jsx(ModalTextarea, { id: 'ncContent', placeholder: '输入快捷指令正文，发送时注入…', minHeight: '120px' }) }),
    ], function() { R.doCreateCmd() }, '创建指令')
  }

  if (R.md === 'project') {
    return modalShell('New Project', null, [
      jsx(ModalField, { key: 'f1', label: '项目名称', children: jsx(ModalInput, { id: 'npName', placeholder: '如：里程运营', autoFocus: true }) }),
      jsx(ModalField, { key: 'f2', label: '项目背景', children: jsx(ModalTextarea, { id: 'npBg', placeholder: '为什么做这个项目' }) }),
      jsx(ModalField, { key: 'f3', label: '项目目标', children: jsx(ModalTextarea, { id: 'npGoal', placeholder: '要达成什么' }) }),
      jsxs('div', { key: 'f4', className: 'grid grid-cols-2 gap-4', children: [
        jsx(ModalField, { label: '截止日期', children: jsx(ModalInput, { id: 'npDue', type: 'date' }) }),
      ]}),
    ], R.doCreateProj, '创建项目')
  }

  if (R.md === 'inbox') {
    function saveInbox() {
      var ti = document.getElementById('inboxTitle').value || ''
      var bo = document.getElementById('inboxBody').value || ''
      if (!ti && !bo) { R.tost('标题和正文至少填一项'); return }
      var now = new Date()
      function p2(n) { return (n < 10 ? '0' : '') + n }
      var ts = now.getFullYear() + '-' + p2(now.getMonth() + 1) + '-' + p2(now.getDate()) + 'T' + p2(now.getHours()) + ':' + p2(now.getMinutes())
      runSpec({ op: 'inbox_create', title: ti || (bo.slice(0, 20) + '…'), body: bo, ts: ts }).then(function(r) {
        R.setMd(null)
        R.tost('已收集')
        try { R.setVw('inbox'); R.load && R.load() } catch(e) {}
      }).catch(function(e) { console.error('[pw] inbox_create failed:', e); R.tost('创建失败') })
    }
    return modalShell('收集灵感', '存入 2. Project/Inbox', [
      jsx(ModalField, { key: 'f1', label: '标题', children: jsx(ModalInput, { id: 'inboxTitle', placeholder: '想收集什么？', autoFocus: true }) }),
      jsx(ModalField, { key: 'f2', label: '正文', children: jsx(ModalTextarea, { id: 'inboxBody', placeholder: '补充细节…（可留空）', minHeight: '120px' }) }),
    ], saveInbox, '保存')
  }

  // Inbox 删除确认弹窗
  if (R.md === 'inbox-del') {
    var delItem = (R.dw && R.dw.item) || {}
    function confirmDel() {
      var p = delItem.path
      if (!p) { R.setMd(null); return }
      runSpec({ op: 'delete_file', path: p }).then(function(r) {
        R.setMd(null)
        R.setDw(null)
        R.setSel(null)
        R.setVw('inbox')
        R.tost('已删除')
      }).catch(function(e) { console.error('[pw] inbox delete failed:', e); R.tost('删除失败') })
    }
    return modalShell('删除这条收集？', null, [
      jsx('div', { key: 'd1', className: 'text-[0.8125rem]', style: { color: BODY, lineHeight: 1.7 }, children: '「' + (delItem.title || '未命名') + '」将被永久删除，不可恢复。' }),
    ], confirmDel, '确认删除')
  }

  var pjn = R.pj(R.sel)
  return modalShell('New Issue', pjn ? '在「' + pjn.title + '」' : null, [
    jsx(ModalField, { key: 'f0', label: '所属项目', children: jsx(Sel, { id: 'ntProject', defaultValue: pjn ? pjn.title : (R.ps[0] ? R.ps[0].title : ''), options: R.ps.map(function(p) { return [p.title, p.title] }) }) }),
    jsx(ModalField, { key: 'f1', label: '任务标题', children: jsx(ModalInput, { id: 'ntTitle', placeholder: '一句话描述要做什么', autoFocus: true }) }),
    jsx(ModalField, { key: 'f2', label: '任务目标', children: jsx(ModalTextarea, { id: 'ntGoal', placeholder: '这个任务要达成什么', minHeight: '90px' }) }),
    jsx(ModalField, { key: 'f3', label: '验收标准（每行一条）', children: jsx(ModalTextarea, { id: 'ntAc', placeholder: '完成 xxx\n数据验证通过' }) }),
    jsxs('div', { key: 'f4', style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '10px' }, children: [
      jsx(ModalField, { label: '开始时间', children: jsx(ModalInput, { id: 'ntStart', type: 'date' }) }),
      jsx(ModalField, { label: '截止日期', children: jsx(ModalInput, { id: 'ntDue', type: 'date' }) }),
    ]}),
    jsxs('div', { key: 'f5', style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px', marginBottom: '10px' }, children: [
      jsx(ModalField, { label: '处理人', children: jsx(HandlerPicker, { id: 'ntHandler', handlers: R.handlers }) }),
      jsx(ModalField, { label: '任务状态', children: jsx(Sel, { id: 'ntStatus', defaultValue: 'open', options: [['open', '待办'], ['In-Progress', '进行中'], ['Waiting', '等待中'], ['Done', '已完成'], ['Dropped', '已取消']] }) }),
      jsx(ModalField, { label: '优先级', children: jsx(Sel, { id: 'ntPriority', defaultValue: 'p1', options: [['p0', 'P0'], ['p1', 'P1'], ['p2', 'P2']] }) }),
    ]}),
    // 重复周期设置（独立组件，自带 state；写 repeat_mode/repeat_unit/repeat_every/repeat_day/repeat_anchor）
    jsx(RepeatFields, { key: 'f6', dueId: 'ntDue' }),
  ], R.doCreateTask, '创建任务')
}

// ─── 重复周期设置（新建任务弹窗内）──────────────────────
function RepeatFields(props) {
  var st = useState(false), enabled = st[0], setEnabled = st[1]
  var ut = useState('week'), unit = ut[0], setUnit = ut[1]
  var ev = useState('1'), every = ev[0], setEvery = ev[1]
  var dw = useState('1'), dayW = dw[0], setDayW = dw[1]
  var dm = useState('1'), dayM = dm[0], setDayM = dm[1]
  // 同步到全局：doCreateTask 直接读 window.__pwRepeatConfig，避免依赖隐藏 input 的 DOM 时序
  var repDay = unit === 'week' ? dayW : unit === 'month' ? dayM : ''
  useEffect(function() {
    var dueEl = document.getElementById(props.dueId)
    var due = dueEl && dueEl.value ? dueEl.value : ''
    var t = new Date()
    var anchor = due || (t.getFullYear() + '-' + String(t.getMonth() + 1).padStart(2, '0') + '-' + String(t.getDate()).padStart(2, '0'))
    window.__pwRepeatConfig = enabled
      ? { mode: 'fixed', unit: unit, every: every || '1', day: repDay || '', anchor: anchor }
      : null
  }, [enabled, unit, every, dayW, dayM, props.dueId])
  return jsxs('div', { className: 'rounded-lg border', style: { borderColor: LINE, background: HOV, padding: '10px 12px', marginTop: '12px' }, children: [
    jsxs('label', { className: 'flex items-center gap-2 cursor-pointer select-none', children: [
      jsx('input', { type: 'checkbox', checked: enabled, onChange: function(e) { setEnabled(e.target.checked) }, style: { accentColor: ACC } }),
      jsx('span', { className: 'text-[0.75rem] font-medium', style: { color: INK }, children: '重复周期任务（完成后自动创建下一个）' }),
    ]}),
    enabled && jsxs('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '8px' }, children: [
      jsxs('div', { className: 'flex items-center gap-1.5', children: [
        jsx('span', { className: 'text-[0.6875rem]', style: { color: MUT }, children: '每' }),
        jsx('input', { id: 'ntRepeatEvery', value: every, onChange: function(e) { setEvery(e.target.value) }, style: { width: '44px', height: '26px', border: '1px solid ' + LINE2, borderRadius: '6px', textAlign: 'center', fontSize: '0.75rem', outline: 'none' } }),
        jsx('select', { id: 'ntRepeatUnit', value: unit, onChange: function(e) { setUnit(e.target.value) }, style: { height: '26px', border: '1px solid ' + LINE2, borderRadius: '6px', fontSize: '0.75rem', outline: 'none', background: '#fff' }, children: [['day','天'],['week','周'],['month','月']].map(function(o) { return jsx('option', { value: o[0], children: o[1] }, o[0]) }) }),
      ]}),
      unit === 'week' && jsxs('div', { className: 'flex items-center gap-1.5', children: [
        jsx('span', { className: 'text-[0.6875rem]', style: { color: MUT }, children: '周' }),
        jsx('select', { id: 'ntRepeatDayW', value: dayW, onChange: function(e) { setDayW(e.target.value) }, style: { height: '26px', border: '1px solid ' + LINE2, borderRadius: '6px', fontSize: '0.75rem', outline: 'none', background: '#fff' }, children: [[1,'周一'],[2,'周二'],[3,'周三'],[4,'周四'],[5,'周五'],[6,'周六'],[7,'周日']].map(function(o) { return jsx('option', { value: String(o[0]), children: o[1] }, o[0]) }) }),
      ]}),
      unit === 'month' && jsxs('div', { className: 'flex items-center gap-1.5', children: [
        jsx('span', { className: 'text-[0.6875rem]', style: { color: MUT }, children: '每月' }),
        jsx('input', { id: 'ntRepeatDayM', type: 'number', min: 1, max: 31, value: dayM, onChange: function(e) { setDayM(e.target.value) }, style: { width: '52px', height: '26px', border: '1px solid ' + LINE2, borderRadius: '6px', textAlign: 'center', fontSize: '0.75rem', outline: 'none' } }),
        jsx('span', { className: 'text-[0.6875rem]', style: { color: MUT }, children: '号' }),
      ]}),
      unit === 'day' && jsx('span', { className: 'text-[0.6875rem]', style: { color: FAINT } }),
    ]}),
  ]})
}

// ─── Field wrapper ───────────────────────────────────────
function Field(props) {
  return jsxs('div', { className: 'mb-5', children: [
    jsx('label', { className: S.fLabel, style: { color: MUT }, children: props.label }),
    props.children,
    props.hint && jsx('div', { className: S.hint, style: { color: MUT }, children: props.hint }),
  ]})
}

// ─── Select（自定义下拉，右侧 chevron）────────────────────
function Sel(props) {
  return jsxs('div', { className: 'relative', children: [
    jsx(Input, { as: 'select', id: props.id, defaultValue: props.defaultValue, options: props.options, classNameExtra: ' w-full appearance-none pr-8 transition-all' }),
    jsx('span', { className: 'pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2', style: { color: MUT }, children: jsx(Codicon, { name: 'chevron-down', className: 'text-[0.6875rem]' }) }),
  ]})
}

// ─── Toggle（开关）───────────────────────────────────────
function Toggle(props) {
  var on = useState(!!props.defaultOn), isOn = on[0], setOn = on[1]
  return jsxs('div', { className: 'flex items-center gap-2.5 cursor-pointer select-none', onClick: function() { setOn(!isOn); if (props.onChange) props.onChange(!isOn) }, children: [
    jsx('span', { className: 'relative inline-block w-8 h-[1.125rem] rounded-full transition-colors', style: { background: isOn ? ACC : TRACK_OFF }, children:
      jsx('span', { className: 'absolute top-[2px] w-[0.875rem] h-[0.875rem] rounded-full bg-white transition-all', style: { left: isOn ? 'calc(100% - 1rem)' : '2px', boxShadow: '0 1px 2px rgba(0,0,0,0.15)' } })
    }),
    jsx('span', { className: 'text-[0.8125rem]', style: { color: BODY }, children: props.label }),
  ]})
}

// ─── Status Filter（分段式筛选控件）────────────────────
var FILTERS = [
  { key: 'all', label: '所有', match: ['open', 'In-Progress', 'Waiting', 'Routine', 'Agent', 'Review', 'Done', 'Dropped'] },
  { key: 'open', label: '规划中', match: ['open'] },
  { key: 'active', label: '进行中/常态化', match: ['In-Progress', 'Waiting', 'Routine', 'Agent', 'Review'] },
  { key: 'done', label: '已完成/放弃', match: ['Done', 'Dropped'] },
]
function StatusFilter(props) {
  return jsx('div', { className: 'inline-flex items-center rounded-full', style: { background: SEG_OFF, padding: '2px' }, children: FILTERS.map(function(o) {
    var sel = props.value === o.key
    return jsx('span', {
      className: 'px-2.5 py-1 rounded-full cursor-pointer select-none transition-all',
      style: {
        background: sel ? '#fff' : 'transparent',
        color: sel ? INK : MUT,
        fontSize: '0.6875rem',
        fontWeight: sel ? 500 : 400,
        boxShadow: sel ? '0 1px 2px rgba(0,0,0,0.08)' : 'none',
      },
      onClick: function() { props.onChange(o.key) },
      children: o.label,
    }, o.key)
  }) })
}
function fltMatch(key, st) { return (FILTERS.find(function(f) { return f.key === key }) || { match: [] }).match.indexOf(st) >= 0 }

// ─── HandlerPicker（combobox：可输入 + 可选择）─────────────
// 输入新值 = 新增；下拉列表 = Obsidian 中 handler 已有值的集合
function HandlerPicker(props) {
  var vF = useState(props.value || props.defaultValue || ''), val = vF[0], setVal = vF[1]
  var oF = useState(false), open = oF[0], setOpen = oF[1]
  // 输入框内的实时文本（未失焦前）
  var tF = useState(null), typed = tF[0], setTyped = tF[1]
  var handlers = props.handlers || []
  var filtered = handlers.filter(function(h) {
    var q = (typed != null ? typed : val).trim().toLowerCase()
    return !q || h.toLowerCase().indexOf(q) >= 0
  })

  // 提交：输入值（新值=新增，旧值=选择），调用 onSave 并关闭下拉
  function commit(v) {
    v = (v || '').trim()
    setVal(v); setTyped(null); setOpen(false)
    if (v && props.onSave) { props.onSave(v) }
  }

  var inputStyle = props.plain
    ? { color: BODY, height: '24px', background: 'transparent', border: 'none', outline: 'none', fontSize: '0.75rem', flex: 1, minWidth: 0 }
    : { color: BODY, height: '32px', background: '#fff', border: '1px solid ' + IN_BRD, borderRadius: '5px', padding: '0 8px', fontSize: '0.75rem', outline: 'none', width: '100%', boxSizing: 'border-box' }

  return jsxs('div', { style: { position: 'relative', display: 'flex', alignItems: 'center', flex: 1, minWidth: 0 }, children: [
    jsx('input', {
      id: props.id,
      value: typed != null ? typed : val,
      placeholder: props.placeholder || '选择或输入处理人',
      style: inputStyle,
      onFocus: function() { setOpen(true) },
      onChange: function(e) { setTyped(e.target.value) },
      onKeyDown: function(e) {
        if (e.key === 'Enter') { commit(typed != null ? typed : val) }
        else if (e.key === 'Escape') { setOpen(false) }
      },
      onBlur: function(e) {
        // 失焦时若输入了新值则提交（新增），否则收起下拉
        var v = (typed != null ? typed : val).trim()
        if (v && v !== val) { setVal(v); if (props.onSave) { props.onSave(v) } }
        setTyped(null); setOpen(false)
      },
    }),
    // 下拉箭头
    jsx('span', {
      style: { position: 'absolute', right: props.plain ? 0 : '6px', color: FAINT, cursor: 'pointer', fontSize: '0.75rem', lineHeight: 1, pointerEvents: 'none', display: 'flex', alignItems: 'center' },
      children: '▾',
    }),
    // 下拉面板
    open && filtered.length > 0 && jsxs('div', {
      style: { position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 30, background: '#fff', border: '1px solid ' + LINE2, borderRadius: '6px', boxShadow: '0 4px 16px rgba(0,0,0,0.1)', marginTop: '4px', maxHeight: '160px', overflowY: 'auto' },
      onMouseDown: function(e) { e.preventDefault() },
      children: filtered.map(function(h) {
        return jsx('div', {
          className: 'pw-hover',
          style: { padding: '5px 10px', fontSize: '0.75rem', cursor: 'pointer', color: h === val ? ACC : BODY, background: h === val ? HOV : 'transparent' },
          onMouseDown: function() { commit(h) },

          children: h,
        }, h)
      }),
    }),
  ]})
}

// ─── Center placeholder ───────────────────────────────────
function Toast(R) {
  if (!R.to) return null
  return jsx('div', {
    style: {
      position: 'fixed', bottom: '32px', left: '50%', transform: 'translateX(-50%)',
      zIndex: 2147483000, background: 'rgba(23,23,28,0.92)',
      boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
      borderRadius: '999px', padding: '8px 16px', fontSize: '13px', fontWeight: 500,
      color: '#fff', maxWidth: '70vw', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
    },
    children: R.to,
  })
}

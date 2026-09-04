// projects-workbench — 全新设计语言（Linear / 现代 SaaS 风格）
// 纯白为底、层级靠留白与字重、圆角更大、阴影更软、着色徽章、分段式标签页、深色 Toast
import { jsx, jsxs, Fragment } from 'react/jsx-runtime'
import { useState, useEffect, useRef } from 'react'
import { cn, host, ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA, Codicon } from '@hermes/plugin-sdk'

var ROUTE = '/projects', SCRIPT = '/Users/ben/.hermes/desktop-plugins/projects-workbench/obsidian-task.py', PROOT = '2. Project/2.1 Project', VAULT = '/Users/ben/Documents/Second Brain/Second Brain'
export default {
  id: 'projects-workbench', name: '项目工作台',
  register: function(ctx) {
    ctx.register({ id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: ROUTE, label: '项目工作台', codicon: 'project' } })
    ctx.register({ id: 'page', area: ROUTES_AREA, data: { path: ROUTE }, render: function() { return jsx(App, {}) } })
    ctx.register({ id: 'palette', area: PALETTE_AREA, data: { label: '项目工作台', codicon: 'project' }, action: function() { host.navigate(ROUTE) } })
  }
}

// ─── Data layer (unchanged) ──────────────────────────────
function sh(cmd) { return host.request('shell.exec', { command: cmd, timeout: 20000 }).then(function(r) { if (r.code !== 0) throw new Error((r.stderr || '').slice(0, 200)); return r.stdout }) }
function b64d(s) { var b = String(s || '').trim(); var bin = atob(b); var bytes = new Uint8Array(bin.length); for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i); return new TextDecoder('utf-8').decode(bytes) }
function jp(o) { var s = b64d(o); return JSON.parse(s) }
function ld() {
  return sh('env HOME=/Users/ben python3 ' + SCRIPT + ' save').then(function(o) {
    var info = JSON.parse(o); var total = info.len; var chunks = []
    for (var i = 0; i < total; i += 3900) chunks.push(i)
    return Promise.all(chunks.map(function(off) {
      return sh('env HOME=/Users/ben python3 ' + SCRIPT + ' read ' + off + ' 3900').then(function(c) { return c.trim() })
    })).then(function(parts) { return jp(parts.join('')) })
  })
}
function b64u(s) { return btoa(unescape(encodeURIComponent(s))) }
function runSpec(spec) { var b = b64u(JSON.stringify(spec)); return sh('env HOME=/Users/ben python3 ' + SCRIPT + ' run "' + b + '"').then(function(o) { var r = jp(o); if (!r.ok) throw new Error(r.error || 'op failed'); return r }) }

// ─── Maps ────────────────────────────────────────────────
var ST = { todo: '待办', in_progress: '进行中', review: '待确认', done: '已完成' }
var PR = { p0: 'P0', p1: 'P1', p2: 'P2' }
var SN = { todo: 'in_progress', in_progress: 'review', review: 'done', done: 'todo' }
var PN = { p0: 'p1', p1: 'p2', p2: 'p0' }
var PST = { active: '进行中', paused: '已暂停', completed: '已完成', archived: '已归档' }

// ─── Design tokens ───────────────────────────────────────
// 墨色文字 / 柔和灰 / 品牌蓝 / 状态色（低饱和）
var INK = '#17171c', BODY = '#55555e', MUT = '#9b9ba4', FAINT = '#c6c6cd'
var LINE = '#ededf0', LINE2 = '#e2e2e7', SBG = '#f6f6f8'
var ACC = '#4a6fff', ACCD = '#3d5ef5', ACCS = '#eef2ff'

// 状态点 / 状态徽章（着色软底）
var SDOT = { todo: '#c6c6cd', in_progress: ACC, review: '#f0a020', done: '#22b573' }
var SBGC = {
  todo: { background: '#f3f3f5', color: '#8a8a92' },
  in_progress: { background: ACCS, color: ACC },
  review: { background: '#fdf4e3', color: '#d98a0b' },
  done: { background: '#e8f8f0', color: '#159a63' },
}
// 优先级徽章
var PBGC = {
  p0: { background: '#fef1f1', color: '#ef4444' },
  p1: { background: '#fdf6e9', color: '#d98a0b' },
  p2: { background: '#f3f3f5', color: '#8a8a92' },
}
// 项目状态点
var PJDOT = { active: ACC, paused: '#f0a020', completed: '#22b573', archived: '#c6c6cd' }

// ─── Helpers ─────────────────────────────────────────────
function dL(d) { if (!d) return ''; if (d === 'today') return '今天'; if (d === 'overdue') return '已逾期'; if (d === 'week') return '本周'; return d }
function todayLocal() { var d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0') }
function dot(color, size) { return jsx('span', { style: { width: size || 7, height: size || 7, borderRadius: 99, background: color, flexShrink: 0, display: 'inline-block' } }) }

// ─── Main component ──────────────────────────────────────
function App() {
  var R = useReducer()
  if (R.vw === 'project' && R.sel) return jsx(ProjectDetail, R)
  if (R.vw === 'tasks') return jsx(AllTasks, R)
  return jsx(ProjectList, R)
}

// ─── Reducer hook (state + actions) ──────────────────────
function useReducer() {
  var ps = useState([]), ts = useState([]), loading = useState(true), err = useState(null)
  var sel = useState(null), vw = useState('projects'), dw = useState(null), tb = useState('inputs')
  var md = useState(null), ef = useState(null), sess = useState([]), to = useState(null)
  var tmRef = useRef(null)

  var setPs = ps[1], setTs = ts[1], setLoading = loading[1], setErr = err[1]
  var setSel = sel[1], setVw = vw[1], setDw = dw[1], setTb = tb[1]
  var setMd = md[1], setEf = ef[1], setSess = sess[1], setTo = to[1]

  function load() {
    setLoading(true); setErr(null)
    ld().then(function(r) { setPs(r.projects || []); setTs(r.tasks || []) })
      .catch(function(e) { setErr((e.message || '').slice(0, 120)) })
      .finally(function() { setLoading(false) })
  }
  useEffect(function() { load() }, [])

  useEffect(function() {
    function onKey(ev) {
      if (ev.key !== 'Escape') return
      if (md[0]) setMd(null)
      else if (dw[0]) setDw(null)
    }
    window.addEventListener('keydown', onKey)
    return function() { window.removeEventListener('keydown', onKey) }
  }, [md[0], dw[0]])

  function pts(proj) { return ts[0].filter(function(x) { return x.project === proj || x.dir === proj }) }
  function pj(n) { return ps[0].filter(function(p) { return p.title === n })[0] }
  function tost(m) { setTo(m); clearTimeout(tmRef.current); tmRef.current = setTimeout(function() { setTo(null) }, 2500) }

  function updateSection(path, sec, text) { return runSpec({ op: 'update_section', path: path, section: sec, text: text }) }
  function toggleAc(path, idx) { return runSpec({ op: 'toggle_ac', path: path, idx: idx }) }

  function doCreateProj() {
    var dir = document.getElementById('npName').value.trim(); if (!dir) { tost('请输入项目名称'); return }
    var bg = document.getElementById('npBg').value.trim(), goal = document.getElementById('npGoal').value.trim()
    var prio = document.getElementById('npPriority').value, today = todayLocal()
    var pC = '---\ntitle: ' + dir + '\nstatus: active\npriority: ' + prio + '\nstart_date: ' + today + '\ntags:\n  - project\n---\n\n# ' + dir + '\n\n## 项目背景\n' + bg + '\n\n## 项目目标\n' + goal + '\n'
    var aC = '# 项目：' + dir + '\n\n## 项目简介\n\n<!-- TASK SNAPSHOT START -->\n## 当前任务状态（自动维护）\n（暂无任务）\n<!-- TASK SNAPSHOT END -->\n'
    runSpec({ op: 'create_project', dir: PROOT + '/' + dir, project_content: pC, agents_content: aC })
      .then(function() { setMd(null); load(); tost('已创建项目「' + dir + '」') })
      .catch(function(e) { setErr((e.message || '').slice(0, 120)) })
  }
  function doCreateTask() {
    var title = document.getElementById('ntTitle').value.trim(); if (!title) { tost('请输入任务标题'); return }
    var pjn = pj(sel[0]); if (!pjn) { tost('项目不存在'); return }
    var goal = document.getElementById('ntGoal').value.trim(), acText = document.getElementById('ntAc').value.trim()
    var acLines = acText ? acText.split('\n').filter(function(x) { return x.trim() }).map(function(x) { return '- [ ] ' + x.trim() }).join('\n') : ''
    var prio = document.getElementById('ntPriority').value, due = document.getElementById('ntDue').value, today = todayLocal()
    var content = '---\ntitle: ' + title + '\nstatus: todo\nnpriority: ' + prio + '\nproject: ' + pjn.title + '\nstart_date: ' + today + (due ? '\ndue: ' + due : '') + '\ntags:\n  - task\n---\n\n# ' + title + '\n\n## 目标\n' + goal + '\n\n## 验收标准\n' + acLines + '\n\n## 推进记录\n- ' + today + ' 创建任务\n'
    var projDir = pjn.dir || pjn.title
    runSpec({ op: 'ensure_dir', path: PROOT + '/' + projDir })
      .then(function() { return runSpec({ op: 'write', path: PROOT + '/' + projDir + '/任务-' + title + '.md', content: content }) })
      .then(function() { setMd(null); load(); tost('已创建任务「' + title + '」') })
      .catch(function(e) { setErr((e.message || '').slice(0, 120)) })
  }
  function doSetField(t_, field, value) {
    var updated = Object.assign({}, t_)
    if (field === 'status') updated.status = value
    if (field === 'priority') updated.priority = value
    setDw(updated)
    var newTs = ts[0].slice()
    for (var i = 0; i < newTs.length; i++) {
      if (newTs[i].path === t_.path) {
        newTs[i] = Object.assign({}, newTs[i])
        if (field === 'status') newTs[i].status = value
        if (field === 'priority') newTs[i].priority = value
      }
    }
    setTs(newTs)
    return runSpec({ op: 'set_property', path: t_.path, field: field, value: value })
      .then(function() { tost('已更新') })
      .catch(function(e) {
        tost('失败：' + ((e && e.message) || '').slice(0, 40))
        setDw(t_)
        var rb = ts[0].slice()
        for (var i = 0; i < rb.length; i++) { if (rb[i].path === t_.path) rb[i] = t_ }
        setTs(rb)
      })
  }
  function doAddLog(t_) {
    var inp = document.getElementById('logInput'); if (!inp) return; var text = inp.value.trim(); if (!text) return
    var now = new Date(), date = String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0') + ' ' + String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0')
    var newLog = { date: date, text: text }
    var updated = Object.assign({}, t_, { logs: (t_.logs || []).concat([newLog]) })
    setDw(updated)
    var newTs = ts[0].slice()
    for (var i = 0; i < newTs.length; i++) {
      if (newTs[i].path === t_.path) {
        newTs[i] = Object.assign({}, newTs[i], { logs: (newTs[i].logs || []).concat([newLog]) })
      }
    }
    setTs(newTs)
    runSpec({ op: 'add_log', path: t_.path, text: date + ' ' + text }).then(function() { tost('已添加推进记录') }).catch(function(e) {
      setErr((e.message || '').slice(0, 120))
      setDw(t_)
      var rbTs = ts[0].slice()
      for (var i = 0; i < rbTs.length; i++) { if (rbTs[i].path === t_.path) rbTs[i] = t_ }
      setTs(rbTs)
    })
    inp.value = ''
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
      .catch(function(e) { setErr((e.message || '').slice(0, 120)) })
  }
  function loadSessions(projDir) {
    return sh('env HOME=/Users/ben python3 ' + SCRIPT + ' sessions "' + projDir + '"').then(function(o) {
      try { return JSON.parse(o).sessions || [] } catch(e) { return [] }
    }).catch(function() { return [] })
  }
  function doCreateSess(pjn) {
    var projDir = pjn.dir || pjn.title
    var cwd = VAULT + '/' + PROOT + '/' + projDir
    host.request('session.create', { cwd: cwd, source: 'desktop', cols: 96 }).then(function(r) {
      if (r && r.stored_session_id) { host.navigate('/' + encodeURIComponent(r.stored_session_id)) }
      else if (r && r.session_id) { host.navigate('/' + encodeURIComponent(r.session_id)) }
      loadSessions(projDir).then(setSess)
      tost('已创建会话')
    }).catch(function(e) { tost('会话创建失败：' + ((e && e.message) || '未知错误')) })
  }

  return {
    ps: ps[0], ts: ts[0], loading: loading[0], err: err[0],
    sel: sel[0], vw: vw[0], dw: dw[0], tb: tb[0], md: md[0], ef: ef[0], sess: sess[0], to: to[0],
    setSel: setSel, setVw: setVw, setDw: setDw, setTb: setTb, setMd: setMd, setEf: setEf, setSess: setSess,
    load: load, pts: pts, pj: pj, tost: tost,
    updateSection: updateSection, toggleAc: toggleAc,
    doCreateProj: doCreateProj, doCreateTask: doCreateTask, doSetField: doSetField,
    doAddLog: doAddLog, doSaveOv: doSaveOv, loadSessions: loadSessions, doCreateSess: doCreateSess,
  }
}

// ═══ 样式系统（全新）══════════════════════════════════════
// 原则：无可见边框的页面层级、大圆角、软阴影、着色徽章、充足留白
var S = {
  // 页面
  page: 'h-full overflow-y-auto bg-white',
  wrap: 'max-w-[1040px] mx-auto px-8 py-8',

  // 文字
  h1: 'text-[1.25rem] font-semibold tracking-[-0.01em]',
  h2: 'text-[0.9375rem] font-semibold',
  body: 'text-[0.8125rem] leading-[1.7]',
  mut: 'text-[0.75rem]',
  cap: 'text-[0.6875rem] font-medium tracking-[0.02em]',

  // 按钮
  btnPrm: 'inline-flex items-center gap-1.5 text-[0.8125rem] font-medium px-4 py-2 rounded-lg text-white cursor-pointer select-none transition-all hover:opacity-90',
  btnSec: 'inline-flex items-center gap-1.5 text-[0.8125rem] font-medium px-3.5 py-2 rounded-lg cursor-pointer select-none transition-all hover:bg-[#f6f6f8]',
  btnTxt: 'inline-flex items-center text-[0.8125rem] px-3 py-2 rounded-lg cursor-pointer select-none transition-colors hover:bg-[#f3f3f5]',
  iconBtn: 'flex items-center justify-center w-8 h-8 rounded-lg cursor-pointer transition-colors hover:bg-[#f3f3f5]',

  // 徽章（软底着色 pill）
  pill: 'inline-flex items-center text-[0.6875rem] font-medium px-2 py-[3px] rounded-full leading-none',

  // 表单
  input: 'w-full bg-white rounded-lg px-3.5 py-3 text-[0.8125rem] border border-[#e2e2e7] text-[#17171c] placeholder:text-[#b8b8bd] outline-none transition-all focus:border-[#4a6fff] focus:shadow-[0_0_0_3px_rgba(74,111,255,0.12)]',
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

// ─── Project List ────────────────────────────────────────
function ProjectList(R) {
  return jsxs(Fragment, { children: [
    jsx('div', { className: S.page, children: jsxs('div', { className: S.wrap, children: [
      // Header
      jsxs('div', { className: 'flex items-end justify-between mb-8', children: [
        jsxs('div', { children: [
          jsxs('div', { className: 'flex items-baseline gap-3', children: [
            jsx('span', { className: S.h1, style: { color: INK }, children: '项目' }),
            jsx('span', {
              className: 'text-[0.8125rem] cursor-pointer transition-colors',
              style: { color: MUT },
              onClick: function() { R.setVw('tasks') },
              children: '全部任务 →',
            }),
          ]}),
          jsx('div', { className: S.mut + ' mt-1.5', style: { color: MUT }, children: R.ps.length + ' 个项目 · ' + R.ts.length + ' 个任务' }),
        ]}),
        jsxs('div', { className: 'flex gap-2 items-center', children: [
          jsx('span', { className: S.iconBtn, style: { color: MUT }, onClick: R.load, children: jsx(Codicon, { name: 'refresh', className: 'text-[0.9375rem]' }) }),
          jsx('span', { className: S.btnPrm, style: { background: ACC, boxShadow: '0 1px 2px rgba(74,111,255,0.25)' }, onClick: function() { R.setMd('project') }, children: '+ 新建项目' }),
        ]}),
      ]}),
      // Content
      R.loading ? jsx(Center, { icon: 'loading', spin: true, text: '加载中…' })
      : R.err ? jsx(Center, { icon: 'error', text: '出错：' + R.err })
      : R.ps.length === 0 ? jsx(Center, { icon: 'project', text: '暂无项目，点击右上角「新建项目」开始' })
      : jsx('div', { className: 'grid gap-4', style: { gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }, children: R.ps.map(function(p) {
          var p_ts = R.pts(p.title), done = p_ts.filter(function(x) { return x.status === 'done' }).length
          var pct = p_ts.length > 0 ? Math.round(done / p_ts.length * 100) : 0
          return jsxs('div', {
            className: S.card + ' p-5 cursor-pointer border border-[#ededf0] hover:shadow-[0_4px_16px_rgba(0,0,0,0.06)] hover:-translate-y-[1px]',
            onClick: function() {
              R.setSel(p.title); R.setVw('project'); R.setTb('inputs'); R.loadSessions(p.dir || p.title).then(R.setSess)
            },
            children: [
              // 标题行
              jsxs('div', { className: 'flex items-center gap-2.5 mb-1.5', children: [
                dot(PJDOT[p.status] || FAINT),
                jsx('span', { className: 'text-[0.9375rem] font-semibold flex-1 min-w-0 truncate', style: { color: INK }, children: p.title }),
                jsx('span', { className: S.pill, style: { background: SBG, color: MUT }, children: PST[p.status] || p.status || '进行中' }),
              ]}),
              // 日期
              jsx('div', { className: S.mut + ' mb-4', style: { color: MUT }, children: (p.start_date || '—') + ' → ' + (p.end_date || '—') }),
              // 进度条（大）
              jsx('div', { className: 'h-[6px] rounded-full overflow-hidden mb-2', style: { background: SBG }, children:
                jsx('div', { className: 'h-full rounded-full transition-all', style: { width: pct + '%', background: 'linear-gradient(90deg,' + ACC + ',#7a95ff)' } })
              }),
              // 底部统计行
              jsxs('div', { className: 'flex items-center mt-3', children: [
                jsxs('span', { className: 'text-[0.75rem]', style: { color: BODY }, children: [
                  jsx('b', { className: 'font-semibold', style: { color: INK }, children: pct + '%' }),
                  ' 完成',
                ]}),
                jsxs('span', { className: 'ml-auto text-[0.75rem]', style: { color: MUT }, children: [
                  done + '/' + p_ts.length + ' 任务',
                  ' · ' + p_ts.reduce(function(s, x) { return s + (x.outputs || []).length }, 0) + ' 产出',
                ]}),
              ]}),
            ],
          }, p.path || p.title)
        }) }),
    ]}) }),
    jsx(Modal, R),
    jsx(Drawer, R),
    jsx(Toast, R),
  ]})
}

// ─── Project Detail（三模块：项目信息 / 当前任务 / 项目会话）──
function ProjectDetail(R) {
  var pjn = R.pj(R.sel), p_ts = R.pts(R.sel)
  var sm = useState(false), sessAll = sm[0], setSessAll = sm[1]
  var groups = [
    { status: 'todo', label: '待办' },
    { status: 'in_progress', label: '进行中' },
    { status: 'review', label: '待确认' },
    { status: 'done', label: '已完成' },
  ]
  var done = p_ts.filter(function(x) { return x.status === 'done' }).length
  var sessShown = sessAll ? R.sess : R.sess.slice(0, 6)

  // 模块标题
  function ModHead(props) {
    return jsxs('div', { className: 'flex items-center mb-3.5', children: [
      jsx('span', { className: S.h2, style: { color: INK }, children: props.title }),
      props.count !== undefined && jsx('span', { className: 'ml-2 ' + S.mut, style: { color: MUT }, children: props.count }),
      jsx('span', { className: 'flex-1' }),
      props.action && jsx('span', {
        className: 'text-[0.8125rem] font-medium cursor-pointer transition-colors hover:opacity-80',
        style: { color: ACC },
        onClick: props.onAction,
        children: props.action,
      }),
    ]})
  }

  return jsxs(Fragment, { children: [
    jsx('div', { className: S.page, children: jsxs('div', { className: S.wrap, children: [
      // Header
      jsxs('div', { className: 'mb-8', children: [
        jsx('span', {
          className: 'inline-flex items-center gap-1 text-[0.8125rem] cursor-pointer mb-4 transition-colors',
          style: { color: MUT },
          onClick: function() { R.setSel(null); R.setVw('projects') },
          children: '← 返回项目列表',
        }),
        jsxs('div', { className: 'flex items-center gap-3', children: [
          dot(pjn ? (PJDOT[pjn.status] || ACC) : ACC, 9),
          jsxs('div', { className: 'flex-1 min-w-0', children: [
            jsxs('div', { className: 'flex items-center gap-2.5', children: [
              jsx('span', { className: S.h1, style: { color: INK }, children: pjn ? pjn.title : R.sel }),
              pjn && jsx('span', { className: S.pill, style: { background: SBG, color: BODY }, children: PST[pjn.status] || pjn.status || '进行中' }),
            ]}),
            pjn && jsx('div', { className: S.mut + ' mt-1.5', style: { color: MUT }, children: (pjn.start_date || '—') + ' → ' + (pjn.end_date || '—') + ' · ' + done + '/' + p_ts.length + ' 任务完成' }),
          ]}),
          jsx('span', { className: S.btnPrm, style: { background: ACC, boxShadow: '0 1px 2px rgba(74,111,255,0.25)' }, onClick: function() { R.setMd('task') }, children: '+ 新建任务' }),
        ]}),
      ]}),

      // ── 模块 1：项目基本信息 ──
      pjn && jsxs('div', { className: 'mb-9', children: [
        jsx(ModHead, { title: '项目信息' }),
        jsxs('div', { className: 'rounded-xl border border-[#ededf0] bg-white', children: [
          jsx(InfoRow, { label: '项目背景', text: pjn.background, editing: R.ef === 'bg', onEdit: function() { R.setEf('bg') }, onSave: R.doSaveOv, onCancel: function() { R.setEf(null) }, last: false }),
          jsx(InfoRow, { label: '项目目标', text: pjn.goal, editing: R.ef === 'goal', onEdit: function() { R.setEf('goal') }, onSave: R.doSaveOv, onCancel: function() { R.setEf(null) }, last: true }),
        ]}),
      ]}),

      // ── 模块 2：当前任务 ──
      jsxs('div', { className: 'mb-9', children: [
        jsx(ModHead, { title: '当前任务', count: done + '/' + p_ts.length + ' 完成', action: '+ 新建任务', onAction: function() { R.setMd('task') } }),
        p_ts.length === 0
          ? jsx('div', { className: 'rounded-xl border border-dashed border-[#e2e2e7] py-10 text-center text-[0.8125rem]', style: { color: MUT }, children: '暂无任务，点击右上角「+ 新建任务」创建' })
          : jsx('div', { className: 'flex flex-col gap-5', children: groups.map(function(g) {
              var gt = p_ts.filter(function(x) { return x.status === g.status })
              if (gt.length === 0) return null
              return jsxs('div', { children: [
                // 分组头
                jsxs('div', { className: 'flex items-center gap-2 mb-2 px-1', children: [
                  dot(SDOT[g.status]),
                  jsx('span', { className: 'text-[0.75rem] font-medium', style: { color: MUT }, children: g.label }),
                  jsx('span', { className: 'text-[0.75rem]', style: { color: FAINT }, children: gt.length }),
                ]}),
                // 任务行
                jsx('div', { className: 'rounded-xl border border-[#ededf0] bg-white overflow-hidden', children: gt.map(function(t, i) {
                  return jsxs('div', {
                    className: 'flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors hover:bg-[#fafafb]' + (i > 0 ? ' border-t border-[#f3f3f5]' : ''),
                    onClick: function() { R.setDw(t) },
                    children: [
                      jsx('span', { className: 'flex-1 min-w-0 text-[0.8125rem] font-medium truncate', style: { color: INK }, children: t.title }),
                      t.due && jsx('span', { className: 'text-[0.6875rem] shrink-0', style: { color: MUT }, children: dL(t.due) }),
                      (t.outputs || []).length > 0 && jsx('span', { className: 'text-[0.6875rem] shrink-0', style: { color: FAINT }, children: (t.outputs || []).length + ' 产出' }),
                      jsx('span', { className: S.pill + ' shrink-0', style: PBGC[t.priority] || { background: SBG, color: MUT }, children: PR[t.priority] || t.priority }),
                      jsx('span', { className: 'shrink-0', style: { color: FAINT }, children: jsx(Codicon, { name: 'chevron-right', className: 'text-[0.75rem]' }) }),
                    ],
                  }, t.path)
                }) }),
              ]}, g.status)
            }) }),
      ]}),

      // ── 模块 3：项目会话 ──
      jsxs('div', { className: 'mb-9', children: [
        jsx(ModHead, { title: '项目会话', count: R.sess.length + ' 个', action: '+ 新会话', onAction: function() { if (pjn) R.doCreateSess(pjn) } }),
        R.sess.length === 0
          ? jsx('div', { className: 'rounded-xl border border-dashed border-[#e2e2e7] py-10 text-center text-[0.8125rem]', style: { color: MUT }, children: '暂无关联会话，点击右上角「+ 新会话」创建' })
          : jsxs(Fragment, { children: [
              jsx('div', { className: 'rounded-xl border border-[#ededf0] bg-white overflow-hidden', children: sessShown.map(function(s, i) {
                return jsxs('div', {
                  className: 'flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors hover:bg-[#fafafb]' + (i > 0 ? ' border-t border-[#f3f3f5]' : ''),
                  onClick: function() { host.navigate('/' + encodeURIComponent(s.id)) },
                  children: [
                    jsx('span', { className: 'shrink-0', style: { color: MUT }, children: jsx(Codicon, { name: 'comment-discussion', className: 'text-[0.9375rem]' }) }),
                    jsx('span', { className: 'flex-1 min-w-0 text-[0.8125rem] truncate', style: { color: INK }, children: s.title }),
                    jsx('span', { className: 'text-[0.6875rem] shrink-0', style: { color: FAINT }, children: s.message_count + ' 条消息' }),
                  ],
                }, s.id)
              }) }),
              R.sess.length > 6 && jsx('div', {
                className: 'mt-2.5 text-center text-[0.8125rem] font-medium py-2 rounded-lg cursor-pointer transition-colors hover:bg-[#f6f6f8]',
                style: { color: ACC },
                onClick: function() { setSessAll(!sessAll) },
                children: sessAll ? '收起' : '加载更多（还有 ' + (R.sess.length - 6) + ' 条）',
              }),
            ] }),
      ]}),
    ]}) }),
    jsx(Drawer, R),
    jsx(Modal, R),
    jsx(Toast, R),
  ]})
}

// ─── All Tasks ───────────────────────────────────────────
function AllTasks(R) {
  return jsxs(Fragment, { children: [
    jsx('div', { className: S.page, children: jsxs('div', { className: S.wrap, children: [
      jsxs('div', { className: 'flex items-baseline gap-3 mb-8', children: [
        jsx('span', { className: 'text-[0.8125rem] cursor-pointer transition-colors', style: { color: MUT }, onClick: function() { R.setVw('projects') }, children: '← 项目' }),
        jsx('span', { className: S.h1, style: { color: INK }, children: '全部任务' }),
        jsx('span', { className: S.mut, style: { color: MUT }, children: R.ts.length + ' 个' }),
      ]}),
      R.ts.length === 0
        ? jsx(Center, { icon: 'checklist', text: '暂无任务' })
        : jsx('div', { className: 'flex flex-col gap-1.5', children: R.ts.map(function(t) {
            var pn = R.pj(t.project || t.dir)
            return jsxs('div', {
              className: 'flex items-center gap-3 px-4 py-3 rounded-xl cursor-pointer transition-all border border-[#ededf0] hover:bg-[#fafafb] hover:border-[#e2e2e7]',
              onClick: function() { R.setSel(t.project || t.dir); R.setVw('project'); R.setDw(t) },
              children: [
                dot(SDOT[t.status] || FAINT),
                jsx('span', { className: 'flex-1 min-w-0 text-[0.8125rem] font-medium truncate', style: { color: INK }, children: t.title }),
                jsx('span', { className: 'text-[0.75rem] shrink-0', style: { color: MUT }, children: pn ? pn.title : (t.project || t.dir) }),
                jsx('span', { className: S.pill, style: SBGC[t.status] || { background: SBG, color: MUT }, children: ST[t.status] || t.status }),
              ],
            }, t.path)
          }) }),
    ]}) }),
    jsx(Drawer, R),
    jsx(Modal, R),
    jsx(Toast, R),
  ]})
}

// ─── Info Row (项目信息卡内的一行：背景/目标) ────────────
function InfoRow(props) {
  return jsxs('div', { className: 'px-5 py-4' + (props.last ? '' : ' border-b border-[#f3f3f5]'), children: [
    jsxs('div', { className: 'flex items-center mb-2', children: [
      jsx('span', { className: S.cap, style: { color: MUT }, children: props.label }),
      jsx('span', {
        className: 'ml-auto text-[0.75rem] font-medium cursor-pointer transition-colors hover:opacity-80',
        style: { color: ACC },
        onClick: props.onEdit,
        children: '编辑',
      }),
    ]}),
    props.editing
      ? jsxs('div', { children: [
          jsx('textarea', {
            className: S.input + ' min-h-[5.5rem] mb-3 resize-y',
            id: 'editInput', defaultValue: props.text || '', autoFocus: true,
          }),
          jsxs('div', { className: 'flex gap-2', children: [
            jsx('span', { className: S.btnPrm, style: { background: ACC }, onClick: props.onSave, children: '保存' }),
            jsx('span', { className: S.btnTxt, style: { color: MUT }, onClick: props.onCancel, children: '取消' }),
          ]}),
        ]})
      : jsx('div', { className: S.body, style: { color: BODY }, children: props.text || '—' }),
  ]})
}

// ─── Task Drawer (右侧滑出) ──────────────────────────────
function Drawer(R) {
  if (!R.dw) return null
  var t = R.dw
  var acItems = (t.acceptance_criteria || []).map(function(a, i) {
    var d = typeof a === 'object' ? a.done : false, txt = typeof a === 'object' ? a.text : a
    return jsxs('div', { className: 'flex items-center gap-2.5 py-1.5 text-[0.8125rem]', style: { color: BODY }, children: [
      jsx('span', {
        className: 'shrink-0 cursor-pointer text-[0.9375rem] leading-none transition-colors',
        style: { color: d ? '#22b573' : FAINT },
        onClick: function() { R.toggleAc(t.path, i).then(function() { R.load() }) },
        children: d ? '☑' : '☐',
      }),
      jsx('span', { style: d ? { textDecoration: 'line-through', color: MUT } : {}, children: txt }),
    ]}, i)
  })
  var logItems = (t.logs || []).map(function(l, i) {
    return jsxs('div', { className: 'flex items-start gap-3 py-2', children: [
      dot(FAINT, 5),
      jsxs('div', { className: 'flex-1 min-w-0', children: [
        jsx('div', { className: 'text-[0.6875rem] font-mono', style: { color: MUT }, children: l.date }),
        jsx('div', { className: 'text-[0.8125rem] leading-relaxed mt-0.5', style: { color: BODY }, children: l.text }),
      ]}),
    ]}, l.date + '-' + i)
  })

  function Sec(props) {
    return jsxs('div', { className: 'mb-7', children: [
      jsx('div', { className: S.cap + ' mb-3', style: { color: MUT }, children: props.label }),
      props.children,
    ]})
  }

  return jsxs('div', {
    className: 'absolute inset-0 z-40',
    style: { background: 'rgba(23,23,28,0.25)' },
    onClick: function() { R.setDw(null) },
    children: [
      jsxs('div', {
        className: 'absolute top-0 right-0 bottom-0 bg-white overflow-y-auto',
        style: { width: 920, maxWidth: '88vw', boxShadow: '-8px 0 40px rgba(0,0,0,0.08)', borderRadius: '16px 0 0 16px' },
        onClick: function(ev) { ev.stopPropagation() },
        children: [
          jsxs('div', { className: 'px-10 py-8', children: [
            // 顶部
            jsxs('div', { className: 'flex items-center justify-between mb-7', children: [
              jsx('span', { className: 'text-[0.8125rem] cursor-pointer transition-colors', style: { color: MUT }, onClick: function() { R.setDw(null) }, children: '← ' + (R.sel || '项目') }),
              jsx('span', { className: S.iconBtn, style: { color: MUT }, onClick: function() { R.setDw(null) }, children: jsx(Codicon, { name: 'close', className: 'text-[0.9375rem]' }) }),
            ]}),
            // 标题区
            jsxs('div', { className: 'mb-7', children: [
              jsx('h2', { className: 'text-[1.375rem] font-semibold leading-tight mb-3', style: { color: INK, letterSpacing: '-0.01em' }, children: t.title }),
              jsxs('div', { className: 'flex items-center gap-2 flex-wrap', children: [
                jsx('span', { className: S.pill, style: SBGC[t.status] || { background: SBG, color: MUT }, children: ST[t.status] || t.status }),
                jsx('span', { className: S.pill, style: PBGC[t.priority] || { background: SBG, color: MUT }, children: PR[t.priority] || t.priority }),
              ]}),
              jsx('div', { className: S.mut + ' mt-3', style: { color: MUT }, children: (t.due ? '截止 ' + dL(t.due) : '无截止日期') + ' · ' + (t.logs || []).length + ' 条推进记录' }),
              // 操作按钮
              jsxs('div', { className: 'flex gap-2 mt-5 flex-wrap', children: [
                jsx('span', { className: S.btnSec, style: { border: '1px solid ' + LINE2, color: BODY }, onClick: function() { R.doSetField(t, 'status', SN[t.status] || 'todo') }, children: '状态：' + (ST[t.status] || t.status) + ' ›' }),
                jsx('span', { className: S.btnSec, style: { border: '1px solid ' + LINE2, color: BODY }, onClick: function() { R.doSetField(t, 'priority', PN[t.priority] || 'p0') }, children: '优先级：' + (PR[t.priority] || t.priority) + ' ›' }),
                t.status !== 'done' && jsx('span', { className: S.btnPrm, style: { background: ACC }, onClick: function() { R.doSetField(t, 'status', 'done') }, children: '✓ 标记完成' }),
              ]}),
            ]}),
            jsx('div', { className: 'h-px mb-7', style: { background: LINE } }),
            // 目标
            jsx(Sec, { label: '目标', children: jsx('div', { className: S.body, style: { color: BODY }, children: t.goal || '—' }) }),
            // 验收标准
            jsx(Sec, { label: '验收标准', children: acItems.length > 0 ? acItems : jsx('span', { className: 'text-[0.8125rem]', style: { color: FAINT }, children: '—' }) }),
            // 推进记录
            jsx(Sec, { label: '推进记录', children: logItems.length > 0 ? logItems : jsx('span', { className: 'text-[0.8125rem]', style: { color: FAINT }, children: '暂无记录' }) }),
            // 添加记录
            jsxs('div', { className: 'flex gap-2 mt-1', children: [
              jsx('input', {
                className: S.input + ' flex-1',
                id: 'logInput', placeholder: '添加推进记录…',
                onKeyDown: function(ev) { if (ev.key === 'Enter') R.doAddLog(t) },
              }),
              jsx('span', { className: S.btnSec, style: { border: '1px solid ' + LINE2, color: BODY }, onClick: function() { R.doAddLog(t) }, children: '添加' }),
            ]}),
          ]}),
        ],
      }),
    ],
  })
}

// ─── Modal (新建项目/任务，参考图风格) ────────────────────
function Modal(R) {
  if (!R.md) return null

  function modalShell(title, subtitle, bodyChildren, onConfirm, confirmLabel) {
    return jsx('div', {
      className: 'absolute inset-0 z-50 flex items-center justify-center',
      style: { background: 'rgba(23,23,28,0.28)' },
      onClick: function() { R.setMd(null) },
      children: jsxs('div', {
        className: 'overflow-hidden bg-white flex flex-col',
        style: { width: 760, maxWidth: '94vw', maxHeight: '88vh', borderRadius: 14, boxShadow: '0 24px 64px rgba(0,0,0,0.18), 0 2px 8px rgba(0,0,0,0.06)' },
        onClick: function(ev) { ev.stopPropagation() },
        children: [
          // Header
          jsxs('div', { className: 'flex items-center justify-between px-8 pt-7 pb-1', children: [
            jsxs('div', { className: 'flex items-baseline gap-2', children: [
              jsx('h3', { className: 'text-[1.0625rem] font-semibold', style: { color: INK }, children: title }),
              subtitle && jsx('span', { className: 'text-[0.8125rem]', style: { color: MUT }, children: subtitle }),
            ]}),
            jsx('span', { className: S.iconBtn, style: { color: MUT }, onClick: function() { R.setMd(null) }, children: jsx(Codicon, { name: 'close', className: 'text-[1rem]' }) }),
          ]}),
          // Body
          jsx('div', { className: 'flex-1 min-h-0 px-8 pt-5 pb-2 overflow-y-auto', children: bodyChildren }),
          // Footer
          jsxs('div', { className: 'flex items-center justify-end gap-1.5 px-8 pt-4 pb-7', children: [
            jsx('span', { className: S.btnTxt, style: { color: BODY }, onClick: function() { R.setMd(null) }, children: '取消' }),
            jsx('span', { className: S.btnPrm, style: { background: ACC, boxShadow: '0 1px 2px rgba(74,111,255,0.3)' }, onClick: onConfirm, children: confirmLabel }),
          ]}),
        ],
      }),
    })
  }

  if (R.md === 'project') {
    return modalShell('新建项目', null, [
      jsx('div', { key: 'f1', className: 'mb-5', children: jsx('input', { className: S.input, id: 'npName', placeholder: '项目名称', autoFocus: true }) }),
      jsx('div', { key: 'f2', className: 'mb-5', children: jsx('textarea', { className: S.input + ' min-h-[7rem] resize-y', id: 'npBg', placeholder: '项目背景（可选）— 为什么做这个项目' }) }),
      jsx('div', { key: 'f3', className: 'mb-5', children: jsx('textarea', { className: S.input + ' min-h-[7rem] resize-y', id: 'npGoal', placeholder: '项目目标（可选）— 要达成什么' }) }),
      jsx(Field, { key: 'f4', label: '优先级', children: jsx(Sel, { id: 'npPriority', defaultValue: 'medium', options: [['high', '高'], ['medium', '中'], ['low', '低']] }) }),
    ], R.doCreateProj, '创建项目')
  }

  var pjn = R.pj(R.sel)
  return modalShell('新建任务', pjn ? '在「' + pjn.title + '」' : null, [
    jsx('div', { key: 'f1', className: 'mb-5', children: jsx('input', { className: S.input, id: 'ntTitle', placeholder: '任务标题 — 一句话描述要做什么', autoFocus: true }) }),
    jsx('div', { key: 'f2', className: 'mb-5', children: jsx('textarea', { className: S.input + ' min-h-[7rem] resize-y', id: 'ntGoal', placeholder: '描述（可选）— 这个任务要达成什么' }) }),
    jsx(Field, { key: 'f3', label: '验收标准（每行一条）', children: jsx('textarea', { className: S.input + ' min-h-[6rem] resize-y', id: 'ntAc', placeholder: '完成 xxx\n数据验证通过' }) }),
    jsxs('div', { key: 'f4', className: 'grid grid-cols-2 gap-5', children: [
      jsx(Field, { label: '优先级', children: jsx(Sel, { id: 'ntPriority', defaultValue: 'p1', options: [['p0', 'P0'], ['p1', 'P1'], ['p2', 'P2']] }) }),
      jsx(Field, { label: '截止日期', children: jsx('input', { className: S.input, id: 'ntDue', type: 'date' }) }),
    ]}),
  ], R.doCreateTask, '创建任务')
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
    jsx('select', {
      className: S.input + ' appearance-none pr-9 cursor-pointer',
      id: props.id, defaultValue: props.defaultValue,
      children: props.options.map(function(o) { return jsx('option', { value: o[0], children: o[1] }, o[0]) }),
    }),
    jsx('span', { className: 'pointer-events-none absolute right-3 top-1/2 -translate-y-1/2', style: { color: MUT }, children: jsx(Codicon, { name: 'chevron-down', className: 'text-[0.75rem]' }) }),
  ]})
}

// ─── Toggle（开关）───────────────────────────────────────
function Toggle(props) {
  var on = useState(!!props.defaultOn), isOn = on[0], setOn = on[1]
  return jsxs('div', { className: 'flex items-center gap-2.5 cursor-pointer select-none', onClick: function() { setOn(!isOn); if (props.onChange) props.onChange(!isOn) }, children: [
    jsx('span', { className: 'relative inline-block w-8 h-[1.125rem] rounded-full transition-colors', style: { background: isOn ? ACC : '#d9d9de' }, children:
      jsx('span', { className: 'absolute top-[2px] w-[0.875rem] h-[0.875rem] rounded-full bg-white transition-all', style: { left: isOn ? 'calc(100% - 1rem)' : '2px', boxShadow: '0 1px 2px rgba(0,0,0,0.15)' } })
    }),
    jsx('span', { className: 'text-[0.8125rem]', style: { color: BODY }, children: props.label }),
  ]})
}

// ─── Toast（深色 pill）───────────────────────────────────
function Toast(R) {
  if (!R.to) return null
  return jsx('div', {
    className: 'absolute bottom-8 left-1/2 -translate-x-1/2 z-50 rounded-full px-4 py-2 text-[0.8125rem] font-medium text-white',
    style: { background: 'rgba(23,23,28,0.92)', boxShadow: '0 4px 16px rgba(0,0,0,0.2)' },
    children: R.to,
  })
}

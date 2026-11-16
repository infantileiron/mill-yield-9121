import {table} from '../components/common/table.js';import {esc,fmt,canEdit} from '../utils/format.js';
const labels={online:'在线（未归档）',mixed:'在线 + 归档',pending:'待迁移',migrating:'迁移中',ready:'可检索',restoring:'恢复中',restored:'已恢复',failed:'迁移失败',corrupt:'归档损坏'};
export const archiveLabel=s=>`<span class="badge ${esc(s)}">${esc(labels[s]||s)}</span>`;
function batchRows(d){return (d.batches||[]).map(b=>[`<strong>${esc(b.batch_code)}</strong><small>${esc(b.received_date)}</small>`,esc(b.line),b.online,b.archived,`<span class="sample-count">${b.online+b.archived}</span>`,archiveLabel(b.state)]);}
export function archivesPage(s){
  const months=s.archives||[];const d=s.archiveDetail;
  return `<header><p class="eyebrow">05 / MONTHLY ARCHIVE</p><h1>月度归档</h1><p>按原粮到货月份归档样本，跨月诊断与报告仍读取完整样本。逐批核对样本数与内容校验后才移出在线区。</p></header>
  <div class="workspace"><section class="paper"><h2>发起迁移</h2>
  <form id="archive-form"><label>到货月份<input name="month" type="month" required value="${esc(months[0]?.month||'2026-11')}"></label><button class="primary" ${canEdit(s.user)?'':'disabled'}>归档该月样本 →</button></form>
  <p class="hint">归档逐批进行：写入归档 → 核对样本数与内容校验 → 才从在线区移除。中断可续跑，重试不会重复写入。同一份样本在诊断中只计一次。</p>
  <h3>恢复已归档月份</h3><div class="review-list">${months.filter(m=>m.archived_samples>0||['ready','failed'].includes(m.status)).map(m=>`<button class="review-choice" data-archive="${esc(m.month)}"><strong>${esc(m.month)}</strong><small>在线 ${m.online_samples} · 归档 ${m.archived_samples}</small>${archiveLabel(m.status)}</button>`).join('')||'<div class="empty">还没有可恢复的归档月份。</div>'}</div>
  </section>
  <section><div class="section-head"><h2>到货月份一览</h2><span>${months.length} 个月</span></div>
  ${table(['月份','状态','在线样本','归档样本','可检索合计','批次进度'],months.map(m=>[`<strong>${esc(m.month)}</strong><small>${m.error?esc(m.error):'校验通过'}</small>`,archiveLabel(m.status),m.online_samples,m.archived_samples,`<span class="sample-count">${m.total_samples}</span>`,`${m.progress?.done_batches??0} / ${m.progress?.total_batches??m.batch_codes.length}${m.new_samples?` · 新增 ${m.new_samples} 待归档`:''}`]))}
  ${d?`<div class="section-head" style="margin-top:34px"><h2>${esc(d.month)} 核对</h2>${archiveLabel(d.status)}</div>
  <div class="metrics"><div><small>在线样本</small><b>${d.online_samples}</b></div><div><small>归档样本</small><b>${d.archived_samples}</b></div><div><small>合计可检索</small><b>${d.total_samples}</b></div><div><small>内容校验</small><b class="${d.verify.ok?'':'rust'}">${d.verify.ok?'通过':'未通过'}</b></div></div>
  ${d.error?`<div class="report-note"><strong>需要处理</strong><p>${esc(d.error)}</p></div>`:''}
  <div class="formula">归档校验和 ${esc(d.checksum||'—')}<br>登记样本 ${d.expected_samples} · 在线 ${d.verify.online} · 归档 ${d.verify.archived}${d.verify.checksum?` · 实算 ${esc(d.verify.checksum)}`:''}</div>
  <div style="display:flex;gap:12px;margin:18px 0"><button class="outline" id="verify-archive" data-month="${esc(d.month)}" style="margin:0">重新校验</button>${canEdit(s.user)&&d.status==='ready'?`<button class="outline" id="restore-archive" data-month="${esc(d.month)}" style="margin:0">恢复该月到在线区</button>`:''}${canEdit(s.user)&&d.status==='failed'?`<button class="outline" id="resume-archive" data-month="${esc(d.month)}" data-op="${esc(d.operation||'archive')}" style="margin:0">${d.operation==='restore'?'续跑恢复':'续跑归档'}</button>`:''}</div>
  ${table(['批次','产线','在线','归档','合计','批次状态'],batchRows(d))}`
  :`<div class="empty">选择左侧月份查看逐批核对明细，或直接发起归档。</div>`}
  </section></div>`;
}

'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const csrf = $('meta[name="csrf-token"]')?.content;
const stages = {pending_interview:'待安排面试',group_interview:'群面',technical_1:'技术一面',technical_2:'技术二面',hr:'HR面',intent:'录用意向',offer_signed:'Offer签约',onboarded:'已入职',rejected:'已淘汰',withdrawn:'候选人退出'};
const statuses = {queued:'排队中',running:'处理中',succeeded:'已完成',failed:'失败'};
const statusClass = {queued:'amber',running:'amber',failed:'red',closed:'gray'};
const badge = (label, cls='') => `<span class="pill ${cls}">${esc(label)}</span>`;
const date = value => value ? new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}) : '—';
const empty = (title, description='') => `<div class="empty"><strong>${esc(title)}</strong>${esc(description)}</div>`;
let toastTimer;
function toast(message, error=false) {
  const dialog=$$('dialog[open]').at(-1);
  const globalToast=$('#toast');
  clearTimeout(toastTimer);
  if(dialog){
    // Native modal dialogs live in the browser top layer, above any body z-index.
    globalToast.className='';
    let notice=$('.dialog-notice',dialog);
    if(!notice){notice=document.createElement('div');dialog.prepend(notice);}
    notice.className=`dialog-notice notice ${error?'danger':''}`;
    notice.setAttribute('role',error?'alert':'status');
    notice.setAttribute('aria-live',error?'assertive':'polite');
    notice.textContent=message;
    if(!error)toastTimer=setTimeout(()=>notice.remove(),4500);
    return;
  }
  globalToast.textContent=message;
  globalToast.className=`show ${error?'error':''}`;
  toastTimer=setTimeout(()=>globalToast.className='',4500);
}
async function api(path, options={}) {
  const headers={'X-CSRF-Token':csrf,...options.headers};
  if (options.body && !(options.body instanceof FormData)) {headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
  const response=await fetch(path,{...options,headers});
  const data=await response.json();
  if (!response.ok) {if(response.status===401) location.href='/login';throw new Error(data.error?.message || '请求失败');}
  return data;
}
function action(fn){return async function(event){
  event?.currentTarget?.closest('dialog')?.querySelector('.dialog-notice')?.remove();
  try{await fn(event);}catch(error){toast(error.message,true);}
};}
function watch(taskId, handlers={}) {
  const stream=new EventSource(`/api/tasks/${taskId}/events`);
  for(const type of ['status','report_patch','completed','failed']) stream.addEventListener(type,event=>{
    const payload=JSON.parse(event.data);
    if(type==='completed'||type==='failed') stream.close();
    Promise.resolve(handlers[type]?.(payload)).catch(error=>toast(error.message,true));
  });
  stream.onerror=()=>handlers.disconnected?.();
  window.addEventListener('pagehide',()=>stream.close(),{once:true});
  return stream;
}
function waitTask(id,onStatus=()=>{}) { return new Promise((resolve,reject)=>watch(id,{status:p=>onStatus(p.message),completed:resolve,failed:p=>reject(new Error(p.message))})); }
async function loadJobFilter() {const {items}=await api('/api/jobs');const selector=$('#job-filter');if(selector)selector.innerHTML='<option value="">全部岗位</option>'+items.map(j=>`<option value="${j.id}">${esc(j.name)}</option>`).join('');return items;}
function pagination(total,page,load){$('#page-info').textContent=`第 ${page} / ${Math.max(1,Math.ceil(total/20))} 页 · 共 ${total} 条`;$('#prev-page').disabled=page<=1;$('#next-page').disabled=page*20>=total;$('#prev-page').onclick=action(()=>load(page-1));$('#next-page').onclick=action(()=>load(page+1));}
$$('.close-dialog').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
$$('dialog').forEach(dialog=>dialog.addEventListener('close',()=>$('.dialog-notice',dialog)?.remove()));
async function deleteRecord(kind,id) {
  const p=await api(`/api/deletion-preview?kind=${kind}&id=${id}`);
  if(p.blocked)throw new Error('有关联任务执行中，请等待完成后删除');
  if(!confirm(`将永久删除 ${p.resumes} 份简历、${p.evaluations} 份报告、${p.recruitments} 条招聘记录。\n涉及岗位：${p.jobs.join('、')||'无'}\n删除后无法恢复，确认继续？`))return false;
  const segment={resume:'resumes',evaluation:'evaluations',candidate:'candidates'}[kind];
  await api(`/api/${segment}/${id}`,{method:'DELETE',body:{confirm:true}});toast('已删除');return true;
}

async function dashboardPage(){
  await loadJobFilter();
  async function load(){
    const query=new URLSearchParams({job_id:$('#job-filter').value,start:$('#start-filter').value,end:$('#end-filter').value});
    const data=await api('/api/dashboard?'+query);
    const cards=[['招聘中岗位',data.stats.open_jobs,'当前开放岗位','▤'],['已评估候选人',data.stats.evaluated,'至少一次成功评估','▥'],['已推进候选人',data.stats.advanced,'当前有效推进','♧'],['已入职候选人',data.stats.onboarded,'曾实际到达入职阶段','✓']];
    $('#stats').innerHTML=cards.map(([label,value,note,icon])=>`<div class="stat-card"><div class="stat-label">${label}</div><span class="stat-icon">${icon}</span><div class="stat-value">${value}</div><div class="stat-note">${note}</div></div>`).join('');
    const max=Math.max(...data.funnel.map(f=>f.count),1);
    $('#funnel').innerHTML=data.funnel.map(f=>`<div class="funnel-row"><span>${esc(f.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${f.count/max*100}%"></div></div><span class="bar-count">${f.count}</span><span class="bar-ratio">${f.ratio===null?'—':f.ratio+'%'}</span></div>`).join('');
    const distMax=Math.max(...data.distribution.map(d=>d.count),1);
    $('#distribution').innerHTML=data.distribution.map(d=>`<div class="distribution-row"><span>${esc(d.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${d.count/distMax*100}%"></div></div><b>${d.count}</b></div>`).join('');
    $('#job-overview').innerHTML=data.jobs.length?data.jobs.map(j=>`<tr><td>${esc(j.name)}</td><td>${badge(j.status==='open'?'招聘中':'已关闭',j.status==='open'?'':'gray')}</td><td>${j.evaluated}</td><td>${j.advanced}</td><td>${j.average_score??'—'}</td><td>${j.onboarded}</td></tr>`).join(''):`<tr><td colspan="6">${empty('还没有岗位','先建立岗位标准，再开始评估简历。')}</td></tr>`;
  }
  $('#filter-dashboard').onclick=action(load);await load();
}

async function jobsPage(){
  let jobs=[],editing=null;
  function criteriaRow(c={}){
    const row=document.createElement('div');row.className='criterion-row';row.dataset.key=c.key||'item_'+crypto.randomUUID().replaceAll('-','').slice(0,12);
    row.innerHTML=`<div class="criterion-top"><label>类型<select class="c-type"><option value="must">必须项</option><option value="bonus">加分项</option></select></label><label>评分项名称<input class="c-name" required value="${esc(c.name)}" placeholder="例如：相关实习经历"></label><label>满分<input class="c-score" type="number" min="0" max="100" required value="${c.max_score??0}"></label><button type="button" class="icon-button remove-criterion" title="删除">×</button></div><div class="criterion-bottom"><label>具体要求<textarea class="c-requirement" rows="2" required placeholder="需要满足的条件">${esc(c.requirement)}</textarea></label><label>评分说明<textarea class="c-rule" rows="2" required placeholder="满足/部分满足/未提供时如何评分">${esc(c.scoring_rule)}</textarea></label></div>`;
    $('.c-type',row).value=c.type||'must';$('.remove-criterion',row).onclick=()=>{row.remove();updateTotal();};$('.c-score',row).oninput=updateTotal;$('#criteria-editor').append(row);updateTotal();
  }
  function updateTotal(){const sum=$$('.c-score').reduce((v,e)=>v+Number(e.value),0);$('#score-total').textContent=`${sum} / 100分`;$('#score-total').className='pill '+(sum===100?'':'amber');}
  function open(job=null){editing=job;$('#job-dialog-title').textContent=job?'编辑岗位':'新建岗位';$('#job-name').value=job?.name||'';$('#job-description').value=job?.description||'';$('#job-jd').value=job?.jd||'';$('#criteria-editor').innerHTML='';(job?.criteria||[{type:'must',max_score:70},{type:'bonus',max_score:30}]).forEach(criteriaRow);$('#draft-status').textContent='';$('#job-dialog').showModal();}
  async function load(){({items:jobs}=await api('/api/jobs'));$('#jobs-grid').innerHTML=jobs.length?jobs.map(j=>`<article class="job-card">${badge(j.status==='open'?'招聘中':'已关闭',j.status==='open'?'':'gray')}<h2>${esc(j.name)}</h2><p class="job-description">${esc(j.description||j.jd.slice(0,90))}</p><div class="meta"><span>${j.criteria.filter(c=>c.type==='must').length} 项硬性要求</span><span>${j.criteria.filter(c=>c.type==='bonus').length} 项加分</span><span>100分</span></div><div class="toolbar"><button class="button edit-job" data-id="${j.id}">查看 / 编辑</button><button class="button toggle-job" data-id="${j.id}">${j.status==='open'?'关闭岗位':'重新开放'}</button></div></article>`).join(''):empty('建立第一个岗位','将JD转成评分标准，让匹配有据可依。');
    $$('.edit-job').forEach(b=>b.onclick=()=>open(jobs.find(j=>j.id===Number(b.dataset.id))));
    $$('.toggle-job').forEach(b=>b.onclick=action(async()=>{const j=jobs.find(j=>j.id===Number(b.dataset.id));await api(`/api/jobs/${j.id}`,{method:'PATCH',body:{status:j.status==='open'?'closed':'open',version:j.version}});await load();}));
  }
  $('#new-job').onclick=()=>open();$('#add-criterion').onclick=()=>criteriaRow();
  $('#job-form').onsubmit=action(async e=>{e.preventDefault();const criteria=$$('.criterion-row').map(row=>({key:row.dataset.key,type:$('.c-type',row).value,name:$('.c-name',row).value,requirement:$('.c-requirement',row).value,max_score:Number($('.c-score',row).value),scoring_rule:$('.c-rule',row).value}));
    await api(editing?`/api/jobs/${editing.id}`:'/api/jobs',{method:editing?'PATCH':'POST',body:{name:$('#job-name').value,jd:$('#job-jd').value,description:$('#job-description').value,criteria,version:editing?.version}});$('#job-dialog').close();toast('岗位已保存');await load();});
  $('#draft-criteria').onclick=action(async()=>{const button=$('#draft-criteria');if(!$('#job-jd').value.trim())throw new Error('请先填写或上传JD');button.disabled=true;try{const {task_id}=await api('/api/jobs/draft',{method:'POST',body:{jd:$('#job-jd').value}});const result=await waitTask(task_id,m=>$('#draft-status').textContent=m);if(!$('#job-name').value)$('#job-name').value=result.name;if(!$('#job-description').value)$('#job-description').value=result.description;$('#criteria-editor').innerHTML='';result.criteria.forEach(criteriaRow);$('#draft-status').textContent='草稿已生成，请检查后保存。';}finally{button.disabled=false;}});
  $('#jd-file').onchange=action(async()=>{const file=$('#jd-file').files[0];if(!file)return;const form=new FormData();form.append('files',file);form.append('purpose','jd');$('#draft-status').textContent='正在上传并解析JD…';const {items}=await api('/api/resumes',{method:'POST',body:form});await waitTask(items[0].task_id,m=>$('#draft-status').textContent=m);const resume=await api(`/api/resumes/${items[0].resume_id}`);$('#job-jd').value=resume.markdown;$('#draft-status').textContent='JD已解析，可生成评分草稿。';});await load();
}

async function uploadPage(){
  let current=null,jobs=[],rows=[];
  const subscriptions=new Map();
  async function load(){({items:rows}=await api('/api/resumes'));$('#resume-list').innerHTML=rows.length?rows.map(r=>`<div class="resume-card"><div><strong>${esc(r.filename)}</strong><p>${r.candidate?esc(r.candidate.name)+' · 已确认候选人':'未确认候选人'} · ${date(r.created_at)}${r.error?' · '+esc(r.error):''}</p></div><div class="toolbar">${badge(statuses[r.status],statusClass[r.status])}${r.status==='succeeded'?`<button class="button primary open-resume" data-id="${r.id}">确认 / 评估 →</button>`:''}${r.status==='failed'?`<button class="button retry-resume" data-id="${r.id}">重试解析</button>`:''}<button class="icon-button delete-resume" data-id="${r.id}" title="删除简历">×</button></div></div>`).join(''):empty('还没有上传简历','上传后可检查解析结果，并选择多个岗位。');
    $$('.open-resume').forEach(b=>b.onclick=action(()=>openResume(Number(b.dataset.id))));
    $$('.retry-resume').forEach(b=>b.onclick=action(async()=>{await api(`/api/resumes/${b.dataset.id}/retry`,{method:'POST',body:{}});await load();}));
    $$('.delete-resume').forEach(b=>b.onclick=action(async()=>{if(await deleteRecord('resume',b.dataset.id))await load();}));
    rows.filter(r=>['queued','running'].includes(r.status)).forEach(r=>{if(!subscriptions.has(r.task_id)){subscriptions.set(r.task_id,watch(r.task_id,{completed:async()=>{subscriptions.delete(r.task_id);await load();},failed:async p=>{subscriptions.delete(r.task_id);toast(p.message,true);await load();}}));}});
  }
  function fillProfile(profile={}){for(const key of ['name','phone','email','education','major'])$('#candidate-'+key).value=profile[key]||'';}
  async function searchExisting(query=''){const {items}=await api('/api/candidates?q='+encodeURIComponent(query));$('#existing-candidate').innerHTML='<option value="">新建候选人（不会覆盖已有资料）</option>'+items.map(c=>`<option value="${c.id}">${esc(c.name)} · ${esc(c.phone||c.email||c.education)}</option>`).join('');}
  async function openResume(id){current=await api(`/api/resumes/${id}`);jobs=(await api('/api/jobs')).items.filter(j=>j.status==='open');$('#resume-title').textContent=current.filename;$('#resume-markdown').value=current.markdown;$('#original-file').href=`/api/resumes/${id}/file`;fillProfile(current.candidate||current.extracted);$('#existing-candidate').disabled=!!current.candidate;$('#confirm-candidate').disabled=!!current.candidate;$$('#profile-fields input').forEach(el=>el.disabled=!!current.candidate);$('#candidate-search').disabled=!!current.candidate;$('#candidate-status').textContent=current.candidate?'已关联 '+current.candidate.name+'，可直接选择岗位评估。':'请检查提取结果，或手动填写信息后确认。';$('#extract-status').textContent='请检查多栏排版、表格或OCR识别结果。';$('#evaluation-links').innerHTML='';$('#job-choices').innerHTML=jobs.length?jobs.map(j=>`<label class="job-choice"><input type="checkbox" value="${j.id}"><span>${esc(j.name)}</span></label>`).join(''):empty('暂无招聘中的岗位','先在岗位管理中建立评分标准。');await searchExisting(current.extracted.phone||current.extracted.email||current.extracted.name||'');$('#resume-dialog').showModal();}
  async function uploadFiles(files){if(!files.length)return;if(files.length>5)throw new Error('每次最多5份文件');if([...files].reduce((sum,f)=>sum+f.size,0)>20*1024*1024)throw new Error('文件总大小超过20MB');const form=new FormData();[...files].forEach(f=>form.append('files',f));const {items}=await api('/api/resumes',{method:'POST',body:form});items.filter(r=>r.duplicates.length).forEach(r=>toast(`${r.filename} 已有相同文件，请确认是否重复候选人`));toast('上传成功，后台正在解析');await load();}
  $('#resume-files').onchange=action(async()=>{await uploadFiles($('#resume-files').files);$('#resume-files').value='';});
  const drop=$('#drop-zone');drop.ondragover=e=>{e.preventDefault();drop.classList.add('dragover');};drop.ondragleave=()=>drop.classList.remove('dragover');drop.ondrop=action(async e=>{e.preventDefault();drop.classList.remove('dragover');await uploadFiles(e.dataTransfer.files);});$('#refresh-resumes').onclick=action(load);
  $('#save-markdown').onclick=action(async()=>{current=await api(`/api/resumes/${current.id}`,{method:'PATCH',body:{markdown:$('#resume-markdown').value,revision:current.revision}});toast('文本已保存');});
  $('#extract-profile').onclick=action(async()=>{const id=current.id;const button=$('#extract-profile');button.disabled=true;try{if($('#resume-markdown').value!==current.markdown){current=await api(`/api/resumes/${id}`,{method:'PATCH',body:{markdown:$('#resume-markdown').value,revision:current.revision}});}const {task_id}=await api(`/api/resumes/${id}/extract`,{method:'POST',body:{}});const result=await waitTask(task_id,m=>$('#extract-status').textContent=m);if(current.id===id){if(!current.candidate)fillProfile(result);$('#extract-status').textContent='提取完成，请核实资料并确认候选人。';await searchExisting(result.phone||result.email||result.name);}}finally{button.disabled=false;}});
  let searchTimer;$('#candidate-search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(action(()=>searchExisting($('#candidate-search').value)),300);};
  $('#confirm-candidate').onclick=action(async()=>{const data={candidate_id:Number($('#existing-candidate').value)||null};for(const key of ['name','phone','email','education','major'])data[key]=$('#candidate-'+key).value;await api(`/api/resumes/${current.id}/candidate`,{method:'POST',body:data});await openRefresh();toast('候选人已确认');await load();});
  async function openRefresh(){current=await api(`/api/resumes/${current.id}`);fillProfile(current.candidate||current.extracted);$('#candidate-status').textContent='已确认：'+current.candidate.name;$('#confirm-candidate').disabled=true;$('#existing-candidate').disabled=true;$('#candidate-search').disabled=true;$$('#profile-fields input').forEach(el=>el.disabled=true);}
  $('#start-evaluations').onclick=action(async()=>{if(!current.candidate_id)throw new Error('请先确认候选人资料');if($('#resume-markdown').value!==current.markdown)throw new Error('解析文本有未保存修改，请先保存');const ids=$$('#job-choices input:checked').map(el=>Number(el.value));if(!ids.length)throw new Error('请选择至少一个岗位');const button=$('#start-evaluations');button.disabled=true;try{const {items}=await api('/api/evaluations',{method:'POST',body:{resume_id:current.id,job_ids:ids,idempotency_key:crypto.randomUUID()}});$('#evaluation-links').innerHTML='<p class="caption">已提交，关闭此窗口不会中止任务。</p>'+items.map(i=>`<p><a class="text-link" href="/evaluations/${i.evaluation_id}">${esc(i.job_name)} · 查看流式报告 →</a></p>`).join('');toast('评估已提交');}finally{button.disabled=false;}});await load();
}

async function evaluationsPage(){await loadJobFilter();let currentPage=1;
  async function load(page=1){currentPage=page;const query=new URLSearchParams({page,job_id:$('#job-filter').value,q:$('#search').value});const data=await api('/api/evaluations?'+query);$('#evaluations-table').innerHTML=data.items.length?data.items.map(e=>`<tr><td>${esc(e.candidate.name)}<small>${esc(e.candidate.education||e.candidate.phone)}</small></td><td>${esc(e.job_name)}</td><td><b>${e.total_score??'—'}</b>${e.total_score!==null?' / 100':''}</td><td>${badge(statuses[e.status],statusClass[e.status])}</td><td>${badge({pending:'待决定',advance:'已推进',reject:'不推进'}[e.decision],e.decision==='pending'?'gray':'')}</td><td>${date(e.created_at)}</td><td><a class="text-link" href="/evaluations/${e.id}">查看报告 →</a></td></tr>`).join(''):`<tr><td colspan="7">${empty('暂无评估记录','上传简历并选择岗位后，报告会显示在这里。')}</td></tr>`;pagination(data.total,page,load);}
  $('#search-evaluations').onclick=action(()=>load());await load();
}

function renderReport(report,final=false,meta={}){
  const list=items=>items?.length?`<ul class="bullet-list">${items.map(i=>`<li>${esc(i)}</li>`).join('')}</ul>`:'<p class="muted">暂无内容</p>';
  let html='';
  if(final){html+=`<section class="panel report-hero"><div><p class="eyebrow">MATCH ANALYSIS</p><h2>${esc(meta.candidate?.name||report.candidate?.name)} <span class="muted">→</span> ${esc(report.job_name)}</h2><p class="muted">${esc(meta.candidate?.education)} · ${esc(meta.candidate?.major)}<br>${esc(meta.model)} · ${date(meta.completed_at)}</p></div><div class="score-circle"><b>${report.total_score}</b><small>匹配分 / 100</small></div></section>`;
    if(report.hard_requirement_failures?.length)html+=`<div class="notice danger"><strong>不满足硬性要求：</strong><ol>${report.hard_requirement_failures.map(i=>`<li>${esc(i.name)}：${esc(i.reason)}</li>`).join('')}</ol>仍可结合实际情况人工推进。</div>`;
    if(report.hard_requirements_to_verify?.length)html+=`<div class="notice amber"><strong>硬性要求待核实：</strong><ol>${report.hard_requirements_to_verify.map(i=>`<li>${esc(i.name)}：${esc(i.reason)}</li>`).join('')}</ol>简历未写不等于不具备该能力。</div>`;
  }
  const relevant=report.relevant_information||{};
  html+=`<section class="panel"><div class="section-heading"><div><h2>岗位相关经历</h2><p>从简历事实提取</p></div>${!final?badge('生成中，待校验','amber'):''}</div><div class="report-columns"><div><h3>技能</h3>${list(relevant.skills)}<h3>实习经历</h3>${list(relevant.internships)}</div><div><h3>项目经历</h3>${list(relevant.projects)}</div></div></section>`;
  const items=report.criteria_results||[];
  html+=`<section class="panel"><div class="section-heading"><div><h2>逐项匹配评分</h2><p>${final?'评分理由与简历原文依据':'分析内容正在生成，最终分数将在完整校验后显示'}</p></div></div>${items.map(item=>{const criterion=meta.snapshot?.criteria.find(c=>c.key===item.criterion_key)||{};const state={met:'满足',partial:'部分满足',unmet:'不满足',unknown:'待核实'}[item.status]||'生成中';return `<div class="criterion-report"><div class="section-heading"><h3>${esc(item.name||criterion.name||item.criterion_key)} ${badge((item.type||criterion.type)==='must'?'必须项':'加分项','gray')}</h3><div>${badge(state,['partial','unknown'].includes(item.status)?'amber':item.status==='unmet'?'red':'')} ${final?`<b>${item.score} / ${item.max_score}</b>`:''}</div></div><p>${esc(item.reason)}</p>${(item.evidence||[]).map(ev=>`<blockquote class="evidence">“${esc(ev.quote)}”<small>${esc(ev.location)}</small></blockquote>`).join('')}</div>`;}).join('')||empty('等待分析评分项')}</section>`;
  html+=`<div class="report-columns"><section class="panel"><h2>匹配优势</h2>${list(report.strengths)}</section><section class="panel"><h2>主要缺口</h2>${list(report.gaps)}</section></div><section class="panel"><h2>面试核实建议</h2>${list(report.interview_questions)}</section>`;return html;
}

async function reportPage(){
  const id=$('#report-app').dataset.id;let evaluation,stream;
  async function load(){evaluation=await api(`/api/evaluations/${id}`);$('#report-file').href=`/api/resumes/${evaluation.resume_id}/file`;$('#snapshot-text').textContent=`岗位：${evaluation.snapshot.job_name}\n标准版本：${evaluation.snapshot.criteria_version}\n简历版本：${evaluation.snapshot.resume_revision}\n\nJD\n${evaluation.snapshot.jd}\n\n评分标准\n${JSON.stringify(evaluation.snapshot.criteria,null,2)}\n\n简历文本\n${evaluation.snapshot.markdown}`;
    $('#retry-evaluation').hidden=['queued','running'].includes(evaluation.status);$('#decision-panel').hidden=evaluation.status!=='succeeded';$('#report-status').textContent=evaluation.status==='succeeded'?'报告已完成并校验。AI提供辅助分析，最终推进由你判断。':evaluation.error||'评估中，页面关闭后任务仍会继续。';$('#report-status').className='notice '+(evaluation.status==='failed'?'danger':'');
    if(evaluation.status==='succeeded'){$('#report-content').innerHTML=renderReport(evaluation.report,true,evaluation);$('#decision-note').value=evaluation.note;$('#decision-state').textContent=evaluation.recruitment?.active?'当前已推进':evaluation.decision==='pending'?'待决定':'当前未推进';}
    if(['queued','running'].includes(evaluation.status)&&!stream){stream=watch(evaluation.task_id,{status:p=>$('#report-status').textContent=p.message,report_patch:p=>$('#report-content').innerHTML=renderReport(p.report,false,evaluation),completed:async()=>{stream=null;await load();},failed:async()=>{stream=null;await load();},disconnected:()=>$('#report-status').textContent='连接暂时中断，正在重新连接；后台任务继续执行。'});}
  }
  for(const [button,value]of [['advance','advance'],['reject','reject']])$('#'+button).onclick=action(async()=>{await api(`/api/evaluations/${id}/decision`,{method:'PUT',body:{decision:value,note:$('#decision-note').value}});toast(value==='advance'?'已推进，可在候选人进度中跟踪':'已设置为不推进');await load();});
  $('#retry-evaluation').onclick=action(async()=>{const {items}=await api(`/api/evaluations/${id}/retry`,{method:'POST',body:{idempotency_key:crypto.randomUUID()}});location.href=`/evaluations/${items[0].evaluation_id}`;});$('#delete-evaluation').onclick=action(async()=>{if(await deleteRecord('evaluation',id))location.href='/evaluations';});await load();
}

async function candidatesPage(){await loadJobFilter();let selected,currentPage=1;
  async function load(page=1){currentPage=page;const query=new URLSearchParams({page,job_id:$('#job-filter').value,stage:$('#stage-filter').value,q:$('#search').value});const data=await api('/api/recruitments?'+query);$('#candidates-table').innerHTML=data.items.length?data.items.map(r=>`<tr><td>${esc(r.candidate.name)}<small>${esc(r.candidate.phone||r.candidate.email)}</small></td><td>${esc(r.job.name)}</td><td><b>${r.score}</b> / 100</td><td>${badge(stages[r.stage],['rejected','withdrawn'].includes(r.stage)?'gray':'')}</td><td>${date(r.updated_at)}</td><td><button class="button open-stage" data-id="${r.id}">更新 / 查看</button></td></tr>`).join(''):`<tr><td colspan="6">${empty('暂无已推进候选人','在匹配报告中点击推进面试后，会进入这里。')}</td></tr>`;$$('.open-stage').forEach(b=>b.onclick=action(()=>open(Number(b.dataset.id))));pagination(data.total,page,load);}
  async function open(id){selected=await api(`/api/recruitments/${id}`);$('#stage-title').textContent=`${selected.candidate.name} · ${selected.job.name}`;$('#new-stage').value=selected.stage;$('#stage-note').value='';$('#basis-report').href=`/evaluations/${selected.basis_evaluation_id}`;$('#stage-history').innerHTML=selected.events.map(e=>`<div class="timeline-row ${e.valid?'':'invalid'}">${esc(stages[e.from_stage]||'推进')} → ${esc(stages[e.to_stage])}<small>${date(e.created_at)} ${e.kind==='correction'?'· 历史纠正':''}</small>${esc(e.note)}</div>`).join('');$('#correction-event').innerHTML='<option value="">正常更新（保留曾到达阶段）</option>'+selected.events.filter(e=>e.valid).map(e=>`<option value="${e.id}">纠正 ${date(e.created_at)} → ${esc(stages[e.to_stage])}</option>`).join('');$('#stage-dialog').showModal();}
  $('#save-stage').onclick=action(async()=>{const eventId=Number($('#correction-event').value);if(eventId&&!confirm('该事件及其后续变更将标记为无效，确定纠正？'))return;await api(`/api/recruitments/${selected.id}/${eventId?'corrections':'stages'}`,{method:'POST',body:{stage:$('#new-stage').value,version:selected.version,note:$('#stage-note').value,event_id:eventId||undefined}});$('#stage-dialog').close();toast('招聘进度已更新');await load(currentPage);});$('#delete-candidate').onclick=action(async()=>{if(await deleteRecord('candidate',selected.candidate_id)){$('#stage-dialog').close();await load();}});$('#search-candidates').onclick=action(()=>load());await load();
}

async function settingsPage(){const cfg=await api('/api/settings/model');$('#api-model').value=cfg.model;$('#api-base').value=cfg.base_url;$('#key-status').textContent=cfg.key_configured?'密钥已配置':'尚未配置';$('#key-status').className='pill '+(cfg.key_configured?'':'amber');$('#settings-form').onsubmit=action(async event=>{event.preventDefault();await api('/api/settings/model',{method:'PUT',body:{model:$('#api-model').value,base_url:$('#api-base').value,api_key:$('#api-key').value}});$('#api-key').value='';toast('模型配置已保存');await settingsPage();});const {items}=await api('/api/maintenance');$('#maintenance').innerHTML=items.length?items.map(t=>`<div class="toolbar">${badge(statuses[t.status],statusClass[t.status])}<span class="muted">任务 #${t.id} ${esc(t.error)}</span>${t.status==='failed'?`<button class="button cleanup-retry" data-id="${t.id}">重试清理</button>`:''}</div>`).join(''):'<p class="caption">暂无未完成的文件清理任务。</p>';$$('.cleanup-retry').forEach(b=>b.onclick=action(async()=>{await api(`/api/tasks/${b.dataset.id}/retry-cleanup`,{method:'POST',body:{}});toast('已安排重试');await settingsPage();}));}

const pages={dashboard:dashboardPage,jobs:jobsPage,upload:uploadPage,evaluations:evaluationsPage,candidates:candidatesPage,settings:settingsPage};
const start=$('#report-app')?reportPage:pages[document.body.dataset.page];if(start)start().catch(error=>toast(error.message,true));

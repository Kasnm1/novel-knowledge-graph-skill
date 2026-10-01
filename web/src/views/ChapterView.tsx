import { useApp } from '../app';
import { Fact, stepAt } from '../model';
import { ChLink, Empty, Ent, Ents, Evidence, Panel, Since } from '../components/common';

/** This chapter only: what happened, who was there and in what state, what changed, what it carries forward. */
export function ChapterView() {
  const { ix, ch } = useApp();
  const c = ix.chapters.get(ch);
  if (!c) return <Empty>没有第 {ch} 章的数据。</Empty>;
  const list = ix.chapterList, i = list.indexOf(ch);
  const prevN = i > 0 ? list[i - 1] : undefined, nextN = i < list.length - 1 ? list[i + 1] : undefined;
  const events = (c.events ?? []).map((id) => [id, ix.m.events[id]] as const).filter(([, e]) => e);
  const present = (c.cast ?? []).filter((r) => r.mode !== 'mentioned');
  const mentioned = (c.cast ?? []).filter((r) => r.mode === 'mentioned');
  const changes = ix.m.facts.filter((f) => f.from === ch);
  const relChanges = ix.m.relations.filter((r) => r.from === ch || r.to === ch || (r.stance ?? []).some((s) => s[0] === ch && s[0] !== r.from));
  const t = ix.m.threads;
  const clues = t.clues.filter((x) => x.from === ch || (x.steps ?? []).some((s) => s[0] === ch) || x.payoffAt === ch);
  const promises = t.promises.filter((x) => x.from === ch || x.resolvedAt === ch || x.status.some((s) => s[0] === ch));
  const routes = t.routes.filter((x) => x.status.some((s) => s[0] === ch) || (x.steps ?? []).some((s) => s[0] === ch));
  const acts = t.acts.filter((x) => x.ch === ch);
  const derived = present.length > 0 && present.every((r) => r.mode === 'derived');

  return (
    <div class="chapter-view">
      <div class="chapter-head">
        <h2>第{ch}章{c.title && <span class="ch-title">{c.title}</span>}</h2>
        <div class="chips">
          {(c.arcs ?? []).map((id) => <span class="chip arc">{ix.arcs.get(id)?.title}</span>)}
          {(c.functions ?? []).map((f) => <span class="chip">{ix.label('narrative_functions', f)}</span>)}
          {c.cliffhanger && c.cliffhanger !== 'none' && <span class="chip hook">章末：{ix.label('cliffhangers', c.cliffhanger)}</span>}
          {c.quality?.grade && <span class={`chip q-${c.quality.grade}`}>审计 {c.quality.score}{c.quality.verified ? ' · 已复核' : ' · 未复核'}</span>}
          {!c.audit && <span class="chip warn" title="这一章没有审计卡：出场与状态确认来自事件推算">无审计卡</span>}
        </div>
      </div>

      <div class="cols">
        <div class="col-main">
          <Panel title="梗概" id="summary">
            {c.summary ? <p class="summary">{c.summary}<Evidence ids={c.ev} /></p> : <Empty>这一章没有梗概。</Empty>}
            <div class="continuity">
              <div class="cont prev">
                <span class="cont-label">承上{prevN != null && <ChLink n={prevN}> · 第{prevN}章</ChLink>}</span>
                <p>{c.prev || ix.chapters.get(prevN ?? -1)?.next || (prevN == null ? '全书开端。' : <span class="muted">未记录与上一章的衔接。</span>)}</p>
              </div>
              <div class="cont next">
                <span class="cont-label">启下{nextN != null && <ChLink n={nextN}> · 第{nextN}章</ChLink>}</span>
                <p>{c.next || <span class="muted">未记录留给下一章的钩子。</span>}</p>
              </div>
            </div>
          </Panel>

          {(c.scenes?.length ?? 0) > 0 && (
            <Panel title="场景" count={c.scenes!.length} id="scenes">
              <ol class="scenes">
                {c.scenes!.map((s) => (
                  <li>
                    <div class="scene-purpose">{s.purpose}</div>
                    <div class="scene-meta">{[s.where, s.when].filter(Boolean).join(' · ')}{s.pov && <> · 视角 <Ent id={s.pov} /></>}</div>
                    <Ents ids={s.who} />
                  </li>
                ))}
              </ol>
            </Panel>
          )}

          <Panel title="情节" count={events.length} id="events">
            {events.length ? (
              <ul class="events">
                {events.map(([, e]) => (
                  <li class={e.death ? 'death' : e.combat ? 'combat' : ''}>
                    <div class="ev-head"><span class="ev-type">{ix.label('event_types', e.type)}</span><strong>{e.title}</strong><Evidence ids={e.ev} /></div>
                    {e.desc && <p>{e.desc}</p>}
                    <div class="ev-meta"><Ents ids={e.who} />{e.where && <> · 于 <Ent id={e.where} /></>}</div>
                  </li>
                ))}
              </ul>
            ) : <Empty>这一章没有记录情节点。</Empty>}
          </Panel>

          {(clues.length + promises.length + routes.length + acts.length) > 0 && (
            <Panel title="本章触及的线索" id="threads">
              <ul class="thread-list">
                {clues.map((x) => {
                  const step = (x.steps ?? []).find((s) => s[0] === ch);
                  const tag = x.from === ch ? '埋下伏笔' : x.payoffAt === ch ? '伏笔回收' : ix.label('progression_kinds', step?.[1]);
                  return <li><span class="tag clue">{tag}</span>{x.label}{step?.[2] && <span class="muted"> — {step[2]}</span>}<Evidence ids={x.ev} /></li>;
                })}
                {promises.map((x) => (
                  <li><span class="tag promise">{x.from === ch ? '立下承诺' : '承诺了结'}</span><Ents ids={x.by} /> {x.terms}
                    {x.resolvedAt === ch && x.resolution && <span class="muted"> — {x.resolution}</span>}<Evidence ids={x.ev} /></li>
                ))}
                {routes.map((x) => {
                  const st = stepAt(x.status, ch)?.[1];
                  const step = (x.steps ?? []).find((s) => s[0] === ch);
                  return <li><span class="tag romance">感情线</span><Ent id={x.who} />：{ix.label('romance_statuses', st)}{step?.[2] && <span class="muted"> — {step[2]}</span>}</li>;
                })}
                {acts.map((x) => (
                  <li><span class="tag intimate">{ix.label('intimacy_act_types', x.type)}</span><Ents ids={x.by} /> → <Ents ids={x.to} />
                    {x.consent && <span class="muted">（{ix.label('consent_contexts', x.consent)}）</span>}<Evidence ids={x.ev} /></li>
                ))}
              </ul>
            </Panel>
          )}
        </div>

        <div class="col-side">
          <Panel title="出场人物" count={present.length} id="cast" extra={derived ? <span class="muted" title="无审计卡，按事件参与者推算">按事件推算</span> : undefined}>
            {present.length ? (
              <ul class="cast">
                {present.map((r) => <CastRow id={r.id} role={r.role} check={r.check} />)}
              </ul>
            ) : <Empty>没有出场记录。</Empty>}
            {mentioned.length > 0 && <div class="mentioned"><span class="muted">提及：</span><Ents ids={mentioned.map((m) => m.id)} max={30} /></div>}
          </Panel>

          <Panel title="本章状态变化" count={changes.length} id="changes">
            {changes.length ? <ul class="changes">{changes.map((f) => <ChangeRow f={f} />)}</ul> : <Empty>没有状态变化。</Empty>}
          </Panel>

          {relChanges.length > 0 && (
            <Panel title="本章关系变化" count={relChanges.length} id="relchanges">
              <ul class="changes">
                {relChanges.map((r) => {
                  const kind = r.from === ch ? '建立' : r.to === ch ? '结束' : '态度';
                  const stance = stepAt(r.stance, ch)?.[1];
                  return (
                    <li><span class={`tag rel-${kind}`}>{kind}</span><Ent id={r.s} /> <span class="rel-type">{ix.label('relations', r.type)}</span> <Ent id={r.t} />
                      {stance && <span class="stance">（{ix.label('stances', stance)}）</span>}<Evidence ids={r.ev} /></li>
                  );
                })}
              </ul>
            </Panel>
          )}

          {c.audit && (
            <Panel title="审计收据" id="audit">
              <ul class="receipts">
                {Object.entries(c.audit).map(([k, v]) => (
                  <li class={v.s === 'none' ? 'none' : 'rec'} title={v.r ?? ''}>
                    <span>{ix.label('audit_items', k)}</span>
                    <b>{v.s === 'none' ? '无' : v.c}</b>
                    {v.s === 'none' && v.r && <em>{v.r}</em>}
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}

function CastRow({ id, role, check }: { id: string; role?: string; check?: string }) {
  const { ix, ch } = useApp();
  const facts = ix.factsAt(id, ch).filter((f) => f.facet !== 'knowledge').slice(0, 6);
  return (
    <li class="cast-row">
      <div class="cast-head">
        <Ent id={id} />
        {check === 'changed' && <span class="mark changed" title="本章状态有变化">▲</span>}
        {check === 'confirmed_unchanged' && <span class="mark confirmed" title="审计确认本章状态未变">✓</span>}
        {role && <span class="role">{role}</span>}
      </div>
      {facts.length > 0 && (
        <div class="cast-facts">
          {facts.map((f) => (
            <span class={`fact${f.from === ch ? ' fresh' : ''}`} title={`${ix.label('facets', f.facet)} · ${f.from === ch ? '本章' : `第${f.from}章起`}`}>
              <i>{ix.label('facets', f.facet)}</i>{f.value}
            </span>
          ))}
        </div>
      )}
    </li>
  );
}

function ChangeRow({ f }: { f: Fact }) {
  const { ix } = useApp();
  return (
    <li>
      <Ent id={f.e} /> <span class="facet">{ix.label('facets', f.facet)}{f.target && <> · <Ent id={f.target} plain /></>}</span>
      <span class="arrow">→</span><b>{f.value}</b>
      {f.reason && <div class="reason">{f.reason}</div>}
      <Evidence ids={f.ev} /> {f.volatile && <Since from={f.from} to={f.to} />}
    </li>
  );
}

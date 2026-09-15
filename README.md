# 小说知识图谱 Skill

一个面向小说与连载文本的证据驱动拆书 Skill，用于把长篇作品整理成**可回放的时序知识图谱、故事圣经、人物/关系/剧情视图、统一 Dashboard，以及可供 AI 继续使用的结构化上下文**。

它的目标不是做普通摘要，而是长期维护一本书中“**发生了什么、什么时候发生、影响了谁、后来如何变化、原文证据在哪里**”。

## 核心能力

- 一书一版本维护一个 canonical run，后续新增章节继续更新同一份数据。
- 抽取并维护人物、身份与别名、物品、能力、地点、组织、关系、感情路线、亲密事件、战斗、承诺、秘密、伏笔、剧情线等信息。
- 所有重要事实尽量关联原文 evidence，可从 Dashboard 一键回到 Reader 查看出处。
- 使用时序模型保留历史变化，不用“最终状态”覆盖过去状态。
- 支持任意章节的 as-of 快照、防剧透输出、章节 A/B 变化比较。
- 支持故事时间（story time）与叙事章节（narrative chapter）双时间轴。
- 支持人物成长、战斗记录、资源、技能分类、世界结构、势力控制、知识传播、死亡/复活、经济与叙事节奏等派生视图。
- 使用 `GraphRuntime` 预索引、fingerprint cache、snapshot checkpoint 和增量工作流，面向超长篇运行。
- 支持 R1–R4 分层检索、动态上下文、resume capsule、candidate closure 和 token telemetry。
- **Token/速度优化不能以降低准确率为代价。** 必要上下文过大时应拆任务或扩大上下文，而不是静默删掉证据或候选。
- 代码负责 ID、时间、引用、证据、防剧透、缓存与一致性；AI 负责需要理解作品本身的语义判断。

## 设计原则

### 一个事实源

`graph.json` 是唯一 canonical story-fact source。

Dashboard、时间线、质量报告、display profile、checkpoint、AI bundle、战斗表、成就表、库存视图等都只是派生产物，不能反向成为第二套事实数据库。

扩展模型中只有 `commitments[]` 是新增的顶层 canonical fact family。不会为了方便展示再创建 `achievements[]`、`duels[]`、`inventory[]`、`deaths[]`、`secrets[]` 等重复事实源。

### 代码守边界，AI 做理解

确定性代码负责：

- stable ID 与引用完整性；
- 时间、状态链和有效区间；
- evidence 与 provenance；
- spoiler cutoff；
- cache/checkpoint 指纹；
- semantic invariant；
- 原子写入与最终验证。

AI 更适合负责：

- 某个事实在当前作品中是否重要；
- 哪些属性值得突出展示；
- 人物/事件的自然语言概括；
- 关系、承诺、伏笔等需要语义理解的判断；
- 何时需要扩大相关历史上下文。

因此不会用大量 `if/else` 把“人物一定看境界/势力、物品一定看稀有度/持有者”之类作品相关语义写死。

## 时序模型

对任意历史章节，都可以生成一个权威快照：

```powershell
python scripts/derive_asof_views.py --graph <graph.json> --chapter 300 --output <snapshot-300.json>
```

快照会在派生视图之前关闭未来人物名/别名、属性、状态、证据、事件、关系、承诺、感情里程碑、伏笔回收和其他带时间的信息，避免只在前端“隐藏文字”造成剧透泄漏。

## 长篇小说的抽取方式

长篇作品不建议一次把整本正文塞进一个上下文。Skill 的设计是：

```text
章节/场景正文
   ↓
候选扫描与相关实体识别
   ↓
构建当前批次所需的完整 evidence closure
   ↓
AI 深度抽取 delta
   ↓
校验并 merge 到 canonical graph
   ↓
下一批继续读取当前状态与必要历史
   ↓
周期性 reconciliation / audit / backfill
```

也就是说，是**分批深读 + 全局可检索记忆 + 必要时向历史扩展上下文**，而不是每批互相失忆。

## 准确率优先的上下文检索

普通抽取可以使用：

```powershell
python scripts/build_extraction_packet.py \
  --graph <graph.json> \
  --excerpts-jsonl <range.jsonl> \
  --chapter-start 301 --chapter-end 310 \
  --candidates <candidates.json> \
  --output <packet.json>
```

检索级别只能向上升级：

- `R1`：当前场景/章节范围 + 直接证据；
- `R2`：R1 + 身份/别名 + 前后状态 + 冲突信息；
- `R3`：R2 + 相关实体 + 完整相关历史 + 远距离证据 + unresolved candidate；
- `R4`：用于 first / last / only / never / all / none 等全局或否定性判断的完整相关覆盖。

身份、秘密、承诺、感情/亲密、伏笔/回收等跨章语义至少需要 R3；全局和否定性判断需要 R4。

如果必要上下文超出预算，预算只能触发**拆批、缓存或更大上下文**，不能偷偷降低 retrieval level。

## 准确率回归门禁

对 retrieval、chunking、state capsule、schema slicing 或 prompt composition 的优化，需要和基线做结构化比较：

```powershell
python scripts/accuracy_regression_gate.py \
  --baseline <baseline.json> \
  --optimized <optimized.json> \
  --report <accuracy.json>
```

至少保证：

- confirmed fact recall 不下降；
- 高风险/mandatory candidate recall 不下降；
- evidence linkage 不下降；
- 不能因为省 Token 增加 unsupported fact 或 false merge。

## 统一 Dashboard

最终使用一个章节同步的 Dashboard，而不是多套互相独立的状态系统。

主要包含：

- 人物/实体仓库；
- 关系图；
- 故事线与集合；
- 人物成长与等级；
- 战斗记录；
- 资源与物品；
- 技能分类；
- 世界结构与势力控制；
- 配角关系与 co-occurrence candidate；
- commitments / favors；
- secrets / knowledge propagation；
- foreshadowing / payoff；
- romance / intimacy；
- mortality / inheritance；
- economy / rules / narrative voice；
- chapter A/B snapshot diff；
- evidence / provenance / unresolved / invariant 质量指标。

### 实体详情

点击人物、物品、地点、组织等实体会打开明显的详情抽屉。

顶部优先展示：

- **首次出现：第 XX 章**
- **重要属性**
- 当前状态
- 当前关系
- 最近重要事件
- 原文证据

如果提供 AI-authored display hints，由 AI 根据当前作品决定“哪些属性重要、如何命名、怎样概括”；程序只验证这些提示引用了真实、当前章节可见的 canonical facts。

没有 AI hints 时，界面使用当前可见属性做中性降级，不按实体类型写死重要性模板。

生成 display profile：

```powershell
python scripts/build_entity_profiles.py \
  --graph <graph.json> \
  --hints <display-hints.json> \
  --output <entity-profiles.json>
```

Dashboard 中的证据可以直接进入：

```text
reader.html?chapter=N&evidence=ID
```

并定位到对应章节与 evidence。

## 质量、变化与双时间轴

```powershell
python scripts/build_quality_report.py --graph <graph.json> --output <quality.json>
python scripts/build_snapshot_diff.py --graph <graph.json> --from-chapter 300 --to-chapter 400 --output <diff.json>
python scripts/build_story_time_view.py --graph <graph.json> --output <story-time.json>
```

质量指标描述的是 evidence 覆盖、provenance 完整度、unresolved 和 invariant 风险，**不是“某条事实为真的概率”**。

Story-time 视图将“读者在哪一章知道这件事”和“故事世界中什么时候发生”分开。程序不会仅凭自由文本硬猜 flashback / flashforward。

## 一键构建最终产物

```powershell
python scripts/build_expansion_artifacts.py \
  --graph <graph.json> \
  --chapters-jsonl <chapters.jsonl> \
  --collection-manifest <dashboard-views.json> \
  --display-hints <display-hints.json> \
  --checkpoint-interval 50 \
  --output-dir <derived-dir>
```

`--display-hints` 是可选的。

防剧透分享构建：

```powershell
python scripts/build_expansion_artifacts.py \
  --graph <graph.json> \
  --chapters-jsonl <chapters.jsonl> \
  --collection-manifest <dashboard-views.json> \
  --cutoff 300 \
  --output-dir <share-dir>
```

最终构建采用 fail-closed：结构验证、扩展验证、semantic invariant、spoiler closure、派生视图、story time、quality、provenance、entity profile、candidate scan、Dashboard 和 Reader 都会分别检查。任何必需步骤失败，最终构建都不会被标记为 complete。

`artifact-manifest.json` 会记录步骤返回码、耗时以及必需产物的 SHA-256 指纹。

## 长篇运行性能

内部实现已经拆分到：

```text
scripts/nkg/
├─ core/
├─ temporal/
├─ extraction/
├─ validation/
├─ views/
└─ domains/
```

核心优化包括：

- `GraphRuntime` 一次建立常用索引；
- fingerprint-safe artifact cache；
- strict snapshot checkpoint；
- 动态 whole-chapter chunk planning；
- resume capsule；
- compact wire delta；
- provenance index；
- affected-scope validation；
- 失败关闭的最终构建流水线。

旧顶层 CLI 仍保留兼容入口，但新能力优先进入模块化 runtime，而不是继续扩大旧单体脚本。

## 安全 GC

`gc_run.py` 默认是 dry-run。

`--apply` 会先写操作计划，再移动文件；支持部分失败回滚和 archive restore。永久 `--purge` 必须通过 manifest 与 fingerprint 校验，避免误删其他目录。

## 安装

把仓库放入 Codex Skills 目录，并保持目录名：

```text
novel-knowledge-graph
```

Windows 默认可使用：

```text
%CODEX_HOME%\skills\novel-knowledge-graph
```

常见路径：

```text
C:\Users\<你>\.codex\skills\novel-knowledge-graph
```

Skill 会通过 `SKILL.md` 的 frontmatter 被发现。运行数据、小说正文和生成的 Dashboard 应放在独立 workspace，而不是 Skill 仓库中。

## 验证

```powershell
python -m unittest discover -s scripts -p "test_*.py"
```

CI 还会使用真实 Chrome/Selenium 检查：

- 非单调章节滑块；
- 多面板章节一致性；
- spoiler marker 泄漏；
- 实体详情时序泄漏；
- snapshot diff / quality UI；
- overlapping evidence highlighting；
- Reader evidence deep link；
- GC apply / rollback / restore / purge；
- accuracy/runtime regression；
- 1200 章 / 450 人物的大型运行 fixture。

当前 v2 合并前完整验收为 **95 / 95 tests passed**，严格代码健康检查为 **0 hard errors**。

## 仓库范围与数据卫生

本仓库只保存可复用的 Skill 本身，**不保存**：

- 小说正文；
- 特定作品的章节拆分结果；
- canonical run；
- 为某本书生成的 Dashboard；
- 私有数据、账号或凭据。

这些内容应保存在独立工作目录，例如：

```text
U:\chaishu\runs
```

Cytoscape runtime 的授权说明位于：

```text
assets/CYTOSCAPE-LICENSE.txt
```

## 相关文档

- `SKILL.md`
- `scripts/NKG_V2_COMMANDS.md`
- `references/architecture-v2.md`
- `references/accuracy-preserving-token-optimization.md`
- `references/display-intelligence-contract.md`
- `references/expansion-schema.md`
- `references/expansion-workflows.md`

## License

当前仓库尚未声明开源许可证。如需以特定开源协议重新分发，请先补充对应 License。

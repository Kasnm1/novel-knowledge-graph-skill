# Evidence-backed style analysis

Style analysis is an analytical view, not a replacement for story facts. Keep observations in a separate run artifact (for example `style-observations.json`) and link every claim to chapter ranges and evidence IDs.

```json
{
  "id": "sty_char_f01_001",
  "scope": "character",
  "entity_id": "char_main",
  "dimension": "speech",
  "claim": "正式场合使用克制短句，亲近关系中增加调侃语气。",
  "chapter_start": 1,
  "chapter_end": 80,
  "stability": "contextual",
  "evidence_ids": [],
  "counterexamples": [],
  "confidence": "inferred"
}
```

Required fields are `scope`, `dimension`, `claim`, chapter range, evidence IDs, confidence (`explicit`, `inferred`, or `uncertain`), and stability (`stable`, `evolving`, or `contextual`). Unsupported subjective labels must not be emitted as facts. Counterexamples and limitations should be recorded whenever the claim is not universal.

Cover these dimensions when evidence permits:

- 作品行文：句长、标点、对话比例、描写密度、段落节奏、章末钩子；
- 叙事方式：视角、时间顺序、倒叙／插叙、聚焦、信息释放、冲突升级；
- 人物刻画：外貌、行为、心理、关系差异与跨阶段变化；
- 关键人物语言：口头禅、语气词、称呼、礼貌等级、句末形式、语言功能；
- 关键人物行为：冲突反应、决策方式、对弱者态度、隐瞒／谈判／行动模式。

The dashboard must distinguish measured statistics from interpretive observations. Show the chapter range, confidence, stability, evidence count, and counterexample count beside every conclusion. When observations across ranges disagree, show both as evolving or contextual instead of averaging them into one timeless trait. Style views may be filtered by character, arc, chapter range, and evidence status, and should link back to the exact source excerpts without exposing internal field names to readers.

Validate this artifact before dashboard generation:

```powershell
python scripts/validate_style_observations.py --graph <graph.json> --style-observations <style-observations.json> --output <style-validation.json>
```

`build_dashboard.py` performs the same validation when it auto-discovers the file beside `graph.json` or receives `--style-observations`.

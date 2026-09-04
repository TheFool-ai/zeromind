# 结构化信息分析工作流实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用安全 DSL 完成元数据初筛、全文分析、确定性评分、自动细筛、结构化结果投影、人工改判、信息流展示和用户笔记。

**Architecture:** 保持现有 Python 模块化单体和 DDD 限界上下文。`workflows` 只负责安全编排，新增 `analysis` 和 `notes` 上下文保存结构化结果与个人资产；原文继续只在工作流运行期存在。FastAPI 提供查询与写入 API，React 提供信息流、分析详情、改判和笔记界面。

**Tech Stack:** Python 3.12、FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、PostgreSQL 16、pytest、React 19、TypeScript 5.8、TanStack Query 5、Vitest、Docker Compose。

## Global Constraints

- 实现依据为 `docs/superpowers/specs/2026-07-30-structured-analysis-workflow-design.md`。
- 初筛和细筛默认由 Agent 自动完成，管理员只通过追加审计记录进行改判。
- 不保存解析出的文章正文、网页快照或可还原全文的输出。
- 每份分析最多保存 5 条金句；金句最长 300 个 Unicode 字符，上下文最长 200 个字符。
- 观点最多 10 条；所有分数均为 0 到 100 的整数。
- 总分由 DSL `score` 节点按权重确定性计算，Agent 不能直接决定最终总分。
- 工作流和分析投影都必须幂等。
- 现有工作流 DSL 保持兼容；未声明 `projection` 的工作流继续返回任意 JSON 对象。
- 不实现比较阅读、多用户注册、个性化学习、收藏、划线、语义搜索、长文 Map/Reduce 或主题聚类。
- 当前工作树中的 `backend/migrations/env.py`、`backend/src/zeromind/shared/migration_config.py` 和 `backend/tests/test_migration_config.py` 属于已有无关改动，任何提交都不得暂存它们。
- 所有功能改动执行测试驱动开发：先提交失败测试证据，再写最小实现，再运行对应测试。
- 每个任务只提交其文件清单内的改动。

---

## 文件结构

### 工作流上下文

- `backend/src/zeromind/workflows/dsl.py`：DSL 类型、映射安全、门禁图约束、投影声明。
- `backend/src/zeromind/workflows/primitives.py`：确定性评分和谓词比较，不依赖数据库或 Agent。
- `backend/src/zeromind/workflows/executor.py`：提前终止语义和瞬态正文清除。
- `backend/src/zeromind/workflows/service.py`：统一协调执行器与结果投影。
- `backend/src/zeromind/bootstrap/runtime.py`：注册 `reference`、`score` 等内置节点处理器。

### 分析上下文

- `backend/src/zeromind/analysis/domain.py`：`ContentAnalysis`、评分维度、观点、金句和改判领域对象。
- `backend/src/zeromind/analysis/schema.py`：`content_analysis_v1` 投影输入校验。
- `backend/src/zeromind/analysis/models.py`：分析、标签和改判的 SQLAlchemy 模型。
- `backend/src/zeromind/analysis/repository.py`：内存与 SQLAlchemy 仓储。
- `backend/src/zeromind/analysis/projector.py`：工作流输出到领域聚合的转换。
- `backend/src/zeromind/analysis/service.py`：查询、游标分页和人工改判应用服务。
- `backend/src/zeromind/analysis/api.py`：分析列表、详情和改判 REST API。

### 笔记上下文

- `backend/src/zeromind/notes/domain.py`：笔记聚合与长度约束。
- `backend/src/zeromind/notes/models.py`：笔记 SQLAlchemy 模型。
- `backend/src/zeromind/notes/repository.py`：内存与 SQLAlchemy 仓储。
- `backend/src/zeromind/notes/service.py`：归属、引用一致性和 CRUD。
- `backend/src/zeromind/notes/api.py`：笔记 REST API。

### 前端

- `frontend/src/pages/analyses.tsx`：信息流列表和过滤。
- `frontend/src/pages/analysis-detail.tsx`：结构化分析、评分、改判和笔记。
- `frontend/src/api/client.ts`：分析与笔记响应类型。
- `frontend/src/app.tsx`：导航和路由。
- `frontend/src/styles.css`：信息流与详情样式。

---

### Task 1: 安全 DSL 字面量、评分和终止门禁

**Files:**

- Create: `backend/src/zeromind/workflows/primitives.py`
- Modify: `backend/src/zeromind/workflows/dsl.py`
- Modify: `backend/src/zeromind/workflows/executor.py`
- Modify: `backend/src/zeromind/workflows/api.py`
- Modify: `backend/src/zeromind/bootstrap/runtime.py`
- Modify: `backend/src/zeromind/bootstrap/app.py`
- Modify: `backend/src/zeromind/bootstrap/tasks.py`
- Modify: `backend/src/zeromind/ingestion/repository.py`
- Test: `backend/tests/workflows/test_dsl.py`
- Test: `backend/tests/workflows/test_primitives.py`
- Test: `backend/tests/workflows/test_executor.py`
- Test: `backend/tests/ingestion/test_repository.py`
- Test: `backend/tests/integration/test_schedule.py`

**Interfaces:**

- Produces `PredicateSpec`, `RejectSpec`, `WorkflowSpec.projection` and node types `reference`, `score`, `gate`.
- Produces `calculate_weighted_score(dimensions: dict[str, object]) -> dict[str, object]`.
- Produces `evaluate_predicate(predicate: dict[str, object]) -> bool`.
- Produces `ReferenceRepository.get_revision(reference_id: UUID, number: int) -> ReferenceRevision`.
- Produces successful gate early termination in `WorkflowExecutor.execute`.
- Later tasks consume `content_analysis_v1` as a recognized projection name and consume gate terminal output as `WorkflowRun.output`.

- [ ] **Step 1: 为 DSL 字面量、投影和门禁图约束编写失败测试**

在 `backend/tests/workflows/test_dsl.py` 增加：

```python
def test_workflow_accepts_literals_and_analysis_projection() -> None:
    spec = parse_workflow_yaml(
        """
name: screened
trigger: {events: [manual]}
projection: content_analysis_v1
nodes:
  - id: score
    type: score
    input:
      dimensions:
        value:
          value: 80
          weight: 1.0
          reason: useful
  - id: gate
    type: gate
    depends_on: [score]
    predicate:
      left: $.steps.score.total
      operator: gte
      right: 70
    reject:
      output: {schema_version: 1, status: fine_rejected}
output: {schema_version: 1, status: qualified}
"""
    )

    assert spec.projection == "content_analysis_v1"
    assert spec.nodes[0].input["dimensions"] == {
        "value": {"value": 80, "weight": 1.0, "reason": "useful"}
    }
```

同时增加以下独立测试：

- `test_workflow_rejects_unknown_projection`；
- `test_gate_requires_predicate_and_reject_output`；
- `test_non_gate_rejects_predicate_configuration`；
- `test_gate_must_be_the_only_node_in_its_topological_layer`；
- `test_every_node_after_gate_must_descend_from_gate`；
- 将现有不安全映射参数改为 `${__import__('os')}`、`$(whoami)`、反引号命令和格式错误的 `$.steps[item]`；
- 普通文本 `software-builders` 和 `Return JSON only.` 必须作为安全字面量通过。

- [ ] **Step 2: 运行 DSL 测试并确认失败**

Run:

```bash
cd backend
../.venv/bin/pytest tests/workflows/test_dsl.py -q
```

Expected: FAIL，Pydantic 报告未知 `projection`、未知 `score`/`gate` 节点类型，普通字面量仍被旧映射规则拒绝。

- [ ] **Step 3: 实现 DSL 类型和精确校验规则**

在 `backend/src/zeromind/workflows/dsl.py` 增加以下公开类型：

```python
from typing import Literal

ProjectionName = Literal["content_analysis_v1"]
PredicateOperator = Literal["gt", "gte", "lt", "lte", "eq", "ne", "in", "not_in"]


class PredicateSpec(BaseModel):
    left: object
    operator: PredicateOperator
    right: object


class RejectSpec(BaseModel):
    output: dict[str, object]
```

将 `NodeSpec.type` 扩展为：

```python
type: Literal[
    "resolve",
    "reference",
    "agent",
    "score",
    "gate",
    "condition",
    "parallel",
    "webhook",
]
```

为 `NodeSpec` 增加：

```python
predicate: PredicateSpec | None = None
reject: RejectSpec | None = None
```

为 `WorkflowSpec` 增加：

```python
projection: ProjectionName | None = None
```

校验规则必须逐条实现：

- `gate` 必须同时具有 `predicate` 和 `reject`；
- 非 `gate` 节点不能具有这两个字段；
- `agent_id` 规则保持不变；
- 路径字符串必须匹配现有 `PATH`；
- 以 `$` 开头但不是合法路径的字符串报错；
- 包含 `${`、`$(`、反引号、`__import__` 或以 `lambda ` 开头的字面量报错；
- 其他字符串、数值、布尔值和空值均为字面量；
- 对 `input`、`predicate.left`、`predicate.right`、`reject.output` 和工作流 `output` 递归执行同一映射校验；
- 每个 `gate` 必须独占一个拓扑层；
- `gate` 之后的所有节点都必须是该 `gate` 的传递后代，确保提前终止没有旁路节点。

- [ ] **Step 4: 为评分和谓词编写失败测试**

创建 `backend/tests/workflows/test_primitives.py`：

```python
import pytest

from zeromind.workflows.primitives import calculate_weighted_score, evaluate_predicate


def test_calculates_weighted_score_with_reasons() -> None:
    result = calculate_weighted_score(
        {
            "depth": {"value": 90, "weight": 0.6, "reason": "Deep evidence"},
            "clarity": {"value": 70, "weight": 0.4, "reason": "Readable"},
        }
    )

    assert result == {
        "total": 82,
        "dimensions": {
            "depth": {
                "value": 90,
                "weight": 0.6,
                "reason": "Deep evidence",
            },
            "clarity": {
                "value": 70,
                "weight": 0.4,
                "reason": "Readable",
            },
        },
    }


@pytest.mark.parametrize(
    ("predicate", "expected"),
    [
        ({"left": 70, "operator": "gte", "right": 70}, True),
        ({"left": "ai", "operator": "eq", "right": "product"}, False),
        ({"left": "ai", "operator": "in", "right": ["ai", "code"]}, True),
    ],
)
def test_evaluates_supported_predicates(
    predicate: dict[str, object],
    expected: bool,
) -> None:
    assert evaluate_predicate(predicate) is expected
```

另加失败用例：

- 加权结果为 `82.5` 时使用普通四舍五入得到 `83`，不使用银行家舍入；
- 分值小于 0、大于 100、为布尔值或非整数；
- 空维度；
- 空理由或超过 2,000 字符；
- 权重非正数或总和不在 `1.0 ± 1e-9`；
- 数值比较两侧类型不兼容；
- `in` 的右侧不是集合。

- [ ] **Step 5: 运行原语测试并确认失败**

Run:

```bash
cd backend
../.venv/bin/pytest tests/workflows/test_primitives.py -q
```

Expected: FAIL with `ModuleNotFoundError: zeromind.workflows.primitives`。

- [ ] **Step 6: 实现纯函数评分与谓词比较**

创建 `backend/src/zeromind/workflows/primitives.py`，公开：

```python
from math import isclose
from operator import eq, ge, gt, le, lt, ne

NUMERIC_OPERATORS = {"gt": gt, "gte": ge, "lt": lt, "lte": le}
EQUALITY_OPERATORS = {"eq": eq, "ne": ne}


def calculate_weighted_score(
    dimensions: dict[str, object],
) -> dict[str, object]:
    normalized: dict[str, dict[str, object]] = {}
    weighted = 0.0
    total_weight = 0.0
    if not dimensions:
        raise ValueError("score dimensions cannot be empty")
    for name, raw in dimensions.items():
        if not isinstance(raw, dict):
            raise ValueError(f"score dimension {name} must be an object")
        value = raw.get("value")
        weight = raw.get("weight")
        reason = raw.get("reason")
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError(f"score dimension {name} value must be an integer from 0 to 100")
        if isinstance(weight, bool) or not isinstance(weight, int | float) or weight <= 0:
            raise ValueError(f"score dimension {name} weight must be positive")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise ValueError(f"score dimension {name} reason is invalid")
        normalized[name] = {
            "value": value,
            "weight": float(weight),
            "reason": reason.strip(),
        }
        weighted += value * float(weight)
        total_weight += float(weight)
    if not isclose(total_weight, 1.0, abs_tol=1e-9):
        raise ValueError("score dimension weights must sum to 1.0")
    return {"total": int(weighted + 0.5), "dimensions": normalized}


def evaluate_predicate(predicate: dict[str, object]) -> bool:
    left = predicate["left"]
    right = predicate["right"]
    operator = str(predicate["operator"])
    if operator in NUMERIC_OPERATORS:
        if (
            isinstance(left, bool)
            or isinstance(right, bool)
            or not isinstance(left, int | float)
            or not isinstance(right, int | float)
        ):
            raise ValueError("numeric gate operands must be numbers")
        return bool(NUMERIC_OPERATORS[operator](left, right))
    if operator in EQUALITY_OPERATORS:
        return bool(EQUALITY_OPERATORS[operator](left, right))
    if operator in {"in", "not_in"}:
        if not isinstance(right, list | tuple | set):
            raise ValueError("membership gate right operand must be a collection")
        present = left in right
        return present if operator == "in" else not present
    raise ValueError(f"unsupported gate operator: {operator}")
```

- [ ] **Step 7: 为门禁提前终止和原文清除编写失败测试**

在 `backend/tests/workflows/test_executor.py` 增加一个工作流：`prepare` → `gate` → `expensive`。门禁阈值为 70，`prepare` 返回 20，拒绝输出为 `{"status": "initial_rejected"}`。

断言：

```python
assert run.status == "completed"
assert run.output == {"status": "initial_rejected"}
assert calls == ["prepare"]
assert [step.node_id for step in run.steps] == ["prepare", "gate"]
assert run.steps[-1].output == {
    "passed": False,
    "operator": "gte",
    "left": 20,
    "right": 70,
    "terminal_status": "initial_rejected",
}
```

再增加一个通过门禁的测试，断言 `expensive` 被调用且工作流使用顶层 `output`。保留并扩展现有瞬态正文测试，确保门禁拒绝输出也不能持久化 `_transient_document` 或正文。

- [ ] **Step 8: 运行执行器测试并确认失败**

Run:

```bash
cd backend
../.venv/bin/pytest tests/workflows/test_executor.py -q
```

Expected: FAIL，执行器没有 `gate` 特殊语义或没有对应处理器。

- [ ] **Step 9: 实现门禁提前终止**

在 `backend/src/zeromind/workflows/executor.py` 增加：

```python
@dataclass(frozen=True, slots=True)
class TerminalNodeResult:
    step_output: dict[str, object]
    workflow_output: dict[str, object]
```

修改每一拓扑层的结果合并逻辑：

1. 普通节点继续返回字典；
2. `gate` 在 `_execute_node` 中解析 `predicate`；
3. 谓词为真时返回 `{"passed": True, ...}`；
4. 谓词为假时解析 `reject.output`，返回 `TerminalNodeResult`；
5. 将 `step_output` 写入步骤记录；
6. 将 `workflow_output` 经过 `persistent_view` 后写入 `run.output`；
7. 设置 `run.status = "completed"` 和完成时间；
8. 保存运行并立即返回；
9. 不创建门禁后的步骤记录。

类型不兼容、缺失映射或拒绝输出不是对象时进入现有失败路径。

- [ ] **Step 10: 增加指定引用修订读取与 `reference`、`score` 运行时处理器**

在 `ReferenceRepository`、`InMemoryReferenceRepository` 和 `SqlAlchemyReferenceRepository` 增加：

```python
async def get_revision(
    self,
    reference_id: uuid.UUID,
    number: int,
) -> ReferenceRevision:
```

找不到时抛出 `KeyError((reference_id, number))`。在
`backend/tests/ingestion/test_repository.py` 覆盖读取历史修订和不存在版本。

在 `build_workflow_executor` 中注册：

```python
async def reference_node(input: dict[str, object]) -> dict[str, object]:
    reference_id = uuid.UUID(str(input["reference_id"]))
    reference = await reference_repository.get_reference(reference_id)
    if reference is None:
        raise ValueError(f"reference_not_found:{reference_id}")
    raw_revision = input.get("revision")
    try:
        revision = (
            await reference_repository.get_current_revision(reference_id)
            if raw_revision is None
            else await reference_repository.get_revision(reference_id, int(str(raw_revision)))
        )
    except KeyError as error:
        raise ValueError(
            f"reference_revision_not_found:{reference_id}:{raw_revision}"
        ) from error
    return {
        "reference_id": str(reference.id),
        "revision": revision.number,
        "subscription_id": str(reference.subscription_id),
        "url": revision.url or reference.original_url,
        "title": revision.title,
        "summary": revision.summary,
        "author": revision.author,
        "published_at": revision.published_at.isoformat() if revision.published_at else None,
        "updated_at": revision.updated_at.isoformat() if revision.updated_at else None,
        "observed_at": revision.observed_at.isoformat(),
    }


async def score_node(input: dict[str, object]) -> dict[str, object]:
    raw = input.get("dimensions")
    if not isinstance(raw, dict):
        raise ValueError("score dimensions must be an object")
    return calculate_weighted_score(raw)
```

将处理器映射增加 `"reference": reference_node` 和 `"score": score_node`。`gate` 由执行器处理，不注册普通处理器。
增加运行失败测试，分别断言缺少引用和缺少指定修订时，`run.error` 包含稳定错误码
`reference_not_found` 与 `reference_revision_not_found`。

- [ ] **Step 11: 扩展校验 API 响应**

在 `WorkflowValidationResponse` 增加：

```python
projection: str | None
terminal_gates: tuple[str, ...]
warnings: tuple[str, ...]
```

`warnings` 对数值阈值小于 0 或大于 100 的门禁给出可读警告，但不阻止任意业务门禁。更新 `backend/tests/workflows/test_api.py` 断言这些字段。

- [ ] **Step 12: 运行工作流、摄取和调度测试**

Run:

```bash
cd backend
../.venv/bin/pytest \
  tests/workflows \
  tests/ingestion/test_repository.py \
  tests/integration/test_schedule.py -q
../.venv/bin/ruff check src/zeromind/workflows src/zeromind/ingestion tests/workflows
../.venv/bin/mypy src
```

Expected: 全部 PASS，ruff 和 mypy 无错误。

- [ ] **Step 13: 提交工作流原语**

```bash
git add \
  backend/src/zeromind/workflows \
  backend/src/zeromind/bootstrap/runtime.py \
  backend/src/zeromind/bootstrap/app.py \
  backend/src/zeromind/bootstrap/tasks.py \
  backend/src/zeromind/ingestion/repository.py \
  backend/tests/workflows \
  backend/tests/ingestion/test_repository.py \
  backend/tests/integration/test_schedule.py
git commit -m "feat: add safe workflow scoring and gates"
```

---

### Task 2: 统一结构化分析领域与持久化

**Files:**

- Create: `backend/src/zeromind/analysis/__init__.py`
- Create: `backend/src/zeromind/analysis/domain.py`
- Create: `backend/src/zeromind/analysis/schema.py`
- Create: `backend/src/zeromind/analysis/models.py`
- Create: `backend/src/zeromind/analysis/repository.py`
- Create: `backend/migrations/versions/0008_content_analyses.py`
- Test: `backend/tests/analysis/test_schema.py`
- Test: `backend/tests/analysis/test_domain.py`
- Test: `backend/tests/analysis/test_repository.py`

**Interfaces:**

- Produces `ContentAnalysisDraftV1.model_validate`.
- Produces immutable `ContentAnalysis` and append-only `AnalysisDecisionOverride`.
- Produces `AnalysisRepository.add`, `get`, `get_by_run`, `get_by_identity`, `list`, `add_override`.
- Produces SQL tables `content_analyses`, `content_analysis_tags`, `analysis_decision_overrides`.
- Task 3 consumes the draft and repository to project workflow results.
- Task 4 consumes query results and override methods for REST API.

- [ ] **Step 1: 为统一投影 Schema 编写失败测试**

创建 `backend/tests/analysis/test_schema.py`，定义一个完整通过结果：

```python
from zeromind.analysis.schema import ContentAnalysisDraftV1


def qualified_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "qualified",
        "reference": {
            "reference_id": "11111111-1111-1111-1111-111111111111",
            "revision": 1,
            "subscription_id": "22222222-2222-2222-2222-222222222222",
            "url": "https://example.com/article",
            "title": "A useful article",
            "summary": "RSS summary",
            "author": "Ada",
            "published_at": "2026-07-30T00:00:00+00:00",
            "updated_at": None,
            "observed_at": "2026-07-30T01:00:00+00:00",
        },
        "screening": {
            "score": 85,
            "reason": "Relevant and substantial",
            "summary": "Metadata screening summary",
            "_execution": {
                "agent_id": "33333333-3333-3333-3333-333333333333",
                "agent_version": 1,
                "provider": "openai",
                "model": "gpt-5-mini",
                "usage": {"input": 50, "output": 10},
            },
        },
        "content": {
            "primary_category": "AI",
            "secondary_categories": ["Engineering"],
            "tags": ["agents", "workflows"],
            "one_sentence_summary": "A practical Agent workflow guide.",
            "summary": "The article explains a practical workflow architecture.",
            "viewpoints": [
                {
                    "statement": "Deterministic gates improve explainability.",
                    "explanation": "Thresholds remain visible and testable.",
                }
            ],
            "key_quotes": [
                {
                    "text": "Keep model judgment separate from deterministic policy.",
                    "context": "The author discusses scoring.",
                }
            ],
            "recommendation_level": "recommended",
            "recommendation_reason": "High information density",
            "scores": {
                "depth": {"value": 90, "reason": "Detailed evidence"},
                "clarity": {"value": 80, "reason": "Clear structure"},
            },
            "_execution": {
                "agent_id": "44444444-4444-4444-4444-444444444444",
                "agent_version": 2,
                "provider": "openai",
                "model": "gpt-5",
                "usage": {"input": 500, "output": 100},
            },
        },
        "score": {
            "total": 86,
            "dimensions": {
                "depth": {
                    "value": 90,
                    "weight": 0.6,
                    "reason": "Detailed evidence",
                },
                "clarity": {
                    "value": 80,
                    "weight": 0.4,
                    "reason": "Clear structure",
                },
            },
        },
    }


def test_accepts_qualified_analysis_projection() -> None:
    draft = ContentAnalysisDraftV1.model_validate(qualified_payload())

    assert draft.status == "qualified"
    assert draft.score is not None
    assert draft.score.total == 86
```

增加下列失败测试，每个测试只修改一个字段：

- `schema_version != 1`；
- 分数为小数、布尔值、负数或大于 100；
- 权重和不等于 1；
- 总分不等于加权计算结果；
- `initial_rejected` 仍携带 `content` 或 `score`；
- `fine_rejected`/`qualified` 缺少 `content` 或 `score`；
- 超过 10 个观点；
- 超过 5 条金句；
- 金句、上下文、摘要、推荐理由或评分理由超过设计上限；
- 任意嵌套值含 `_transient_document`、键名 `text` 对应大段正文或字符串 `ARTICLE BODY MUST NOT BE STORED`。

- [ ] **Step 2: 运行 Schema 测试并确认失败**

Run:

```bash
cd backend
../.venv/bin/pytest tests/analysis/test_schema.py -q
```

Expected: FAIL with `ModuleNotFoundError: zeromind.analysis`。

- [ ] **Step 3: 实现 Pydantic v1 投影契约**

在 `backend/src/zeromind/analysis/schema.py` 定义并使用 `ConfigDict(extra="forbid")`：

```python
class ExecutionDraft(BaseModel):
    agent_id: UUID
    agent_version: int = Field(ge=1)
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=255)
    usage: dict[str, int | float] = Field(default_factory=dict)


class ScreeningDraft(BaseModel):
    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=2000)
    summary: str | None = Field(default=None, max_length=1000)
    execution: ExecutionDraft = Field(alias="_execution")


class ViewpointDraft(BaseModel):
    statement: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=2000)


class KeyQuoteDraft(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    context: str | None = Field(default=None, max_length=200)


class ScoreDimensionDraft(BaseModel):
    value: int = Field(ge=0, le=100)
    weight: float = Field(gt=0)
    reason: str = Field(min_length=1, max_length=2000)
```

继续定义 `ReferenceDraft`、`ContentDraft`、`ScoreDraft` 和
`ContentAnalysisDraftV1`。`ContentAnalysisDraftV1` 的 `model_validator`
严格执行状态形状、权重总和、确定性总分和正文泄露扫描。

正文泄露扫描只检查保留的临时标识和超过字段上限的内容，不因为正常金句中出现普通单词 `text` 而误报。

- [ ] **Step 4: 为领域对象和人工改判编写失败测试**

创建 `backend/tests/analysis/test_domain.py`，覆盖：

```python
def test_effective_decision_uses_latest_override() -> None:
    analysis = make_analysis(generated_status="fine_rejected")
    first = analysis.add_override(
        decision="qualified",
        reason="Manual review found original evidence.",
        actor_subject="admin",
        now=datetime(2026, 7, 30, 2, tzinfo=UTC),
    )
    second = analysis.add_override(
        decision="rejected",
        reason="The evidence is outdated after a second review.",
        actor_subject="admin",
        now=datetime(2026, 7, 30, 3, tzinfo=UTC),
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert analysis.effective_decision == "rejected"
```

另行覆盖：改判理由不足 10 字符、超过 2,000 字符、未知 decision、空 actor 和相同时间下仍按 sequence 决定最新记录。

- [ ] **Step 5: 实现领域对象**

在 `backend/src/zeromind/analysis/domain.py` 定义：

```python
AnalysisStatus = Literal["initial_rejected", "fine_rejected", "qualified"]
EffectiveDecision = Literal["qualified", "rejected"]


@dataclass(frozen=True, slots=True)
class ScoreDimension:
    value: int
    weight: float
    reason: str


@dataclass(frozen=True, slots=True)
class Viewpoint:
    statement: str
    explanation: str


@dataclass(frozen=True, slots=True)
class KeyQuote:
    text: str
    context: str | None


@dataclass(frozen=True, slots=True)
class AnalysisDecisionOverride:
    id: uuid.UUID
    analysis_id: uuid.UUID
    sequence: int
    decision: EffectiveDecision
    reason: str
    actor_subject: str
    created_at: datetime
```

`ContentAnalysis` 使用 `slots=True`，并明确包含 `source_name`、
`source_feed_url`、`title`、`original_url`、`author`、`published_at` 和
`observed_at` 等卡片溯源字段。生成分析字段不可被更新，只允许 `add_override`
向内部列表追加新对象。`effective_decision` 返回最新 override，否则把
`qualified` 映射为 `qualified`，其他生成状态映射为 `rejected`。

- [ ] **Step 6: 为 SQLAlchemy 仓储编写失败测试**

在 `backend/tests/analysis/test_repository.py` 建立 SQLite 内存表并测试：

1. 分析聚合及标签可以完整往返；
2. 同一 `(reference_id, reference_revision, workflow_definition_id, workflow_definition_version)` 拒绝重复；
3. `workflow_run_id` 拒绝重复；
4. 添加 override 使用单事务追加 sequence 并更新物化的 `effective_decision`；
5. `get_by_run` 和 `get_by_identity` 返回同一个聚合；
6. 按 generated/effective status、最低分、分类、标签和订阅源过滤；
7. 按 `total_score DESC NULLS LAST`、内容时间 DESC、ID DESC 稳定排序；游标中的
   `sort_score` 对空总分固定使用 `-1`，编码和数据库比较必须采用同一规则。

固定断言示例：

```python
assert restored.reference_id == analysis.reference_id
assert restored.tags == ("agents", "workflows")
assert restored.dimensions["depth"].value == 90
assert restored.effective_decision == "qualified"
```

- [ ] **Step 7: 运行仓储测试并确认失败**

Run:

```bash
cd backend
../.venv/bin/pytest tests/analysis/test_repository.py -q
```

Expected: FAIL because models and repository do not exist。

- [ ] **Step 8: 创建分析数据库模型和迁移**

`ContentAnalysisModel` 使用独立列保存可筛选字段：

```python
class ContentAnalysisModel(Base):
    __tablename__ = "content_analyses"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    reference_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    reference_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    subscription_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    workflow_definition_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    workflow_definition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True)
    generated_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    effective_decision: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(300), nullable=False)
    source_feed_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    original_url: Mapped[str | None] = mapped_column(String(4096))
    author: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    screening: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    primary_category: Mapped[str | None] = mapped_column(String(160), index=True)
    secondary_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    one_sentence_summary: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    viewpoints: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    key_quotes: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    total_score: Mapped[int | None] = mapped_column(Integer, index=True)
    dimensions: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    recommendation_level: Mapped[str | None] = mapped_column(String(80))
    recommendation_reason: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

`reference_id`、`subscription_id`、`workflow_definition_id` 和
`workflow_run_id` 分别使用指向现有领域表的外键；删除内容引用时级联删除分析，
其他三种关系使用 `RESTRICT`。`effective_decision` 是为了查询性能维护的派生读模型
字段，人工改判只更新该字段，不修改任何生成证据。

增加唯一约束 `uq_content_analysis_identity`。`ContentAnalysisTagModel` 使用
`(analysis_id, tag)` 复合唯一约束并给 `tag` 建索引。
`AnalysisDecisionOverrideModel` 使用 `(analysis_id, sequence)` 唯一约束。

迁移 `0008_content_analyses.py` 的 `down_revision` 必须是
`0007_rsshub_instances`，升级创建三张表和上述索引，降级按逆序删除。

- [ ] **Step 9: 实现仓储协议和两种仓储**

在 `backend/src/zeromind/analysis/repository.py` 定义：

```python
@dataclass(frozen=True, slots=True)
class AnalysisQuery:
    generated_status: str | None = None
    effective_decision: str | None = "qualified"
    minimum_score: int | None = None
    category: str | None = None
    tag: str | None = None
    subscription_id: uuid.UUID | None = None
    reference_id: uuid.UUID | None = None
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    limit: int = 20
    cursor: tuple[int, datetime, uuid.UUID] | None = None


class AnalysisRepository(Protocol):
    async def add(self, analysis: ContentAnalysis) -> ContentAnalysis: ...
    async def get(self, analysis_id: uuid.UUID) -> ContentAnalysis | None: ...
    async def get_by_run(self, run_id: uuid.UUID) -> ContentAnalysis | None: ...
    async def get_by_identity(
        self,
        reference_id: uuid.UUID,
        reference_revision: int,
        workflow_definition_id: uuid.UUID,
        workflow_definition_version: int,
    ) -> ContentAnalysis | None: ...
    async def list(self, query: AnalysisQuery) -> tuple[ContentAnalysis, ...]: ...
    async def add_override(
        self,
        override: AnalysisDecisionOverride,
    ) -> ContentAnalysis: ...
```

SQLAlchemy `add_override` 必须锁定分析行、读取最大 sequence、插入下一条 override、
更新 `effective_decision` 并在同一事务提交。

- [ ] **Step 10: 运行分析领域测试、迁移检查和类型检查**

Run:

```bash
cd backend
../.venv/bin/pytest tests/analysis -q
../.venv/bin/alembic upgrade head --sql >/tmp/zeromind-analysis-migration.sql
../.venv/bin/ruff check src/zeromind/analysis tests/analysis migrations/versions/0008_content_analyses.py
../.venv/bin/mypy src
```

Expected: 全部测试通过；Alembic SQL 生成成功；ruff 和 mypy 无错误。

- [ ] **Step 11: 提交分析持久化**

```bash
git add \
  backend/src/zeromind/analysis \
  backend/migrations/versions/0008_content_analyses.py \
  backend/tests/analysis
git commit -m "feat: persist canonical content analyses"
```

---

### Task 3: 工作流结果投影与统一运行服务

**Files:**

- Create: `backend/src/zeromind/analysis/projector.py`
- Create: `backend/src/zeromind/workflows/service.py`
- Modify: `backend/src/zeromind/workflows/domain.py`
- Modify: `backend/src/zeromind/workflows/api.py`
- Modify: `backend/src/zeromind/bootstrap/app.py`
- Modify: `backend/src/zeromind/bootstrap/tasks.py`
- Test: `backend/tests/analysis/test_projector.py`
- Test: `backend/tests/workflows/test_service.py`
- Test: `backend/tests/workflows/test_api.py`
- Test: `backend/tests/integration/test_schedule.py`

**Interfaces:**

- Produces `AnalysisProjector.project(definition, run) -> ContentAnalysis | None`.
- Produces `WorkflowRunService.execute(definition_id, trigger, idempotency_key) -> WorkflowRun`.
- API 和 Worker 后续只调用 `WorkflowRunService`，不直接调用 `WorkflowExecutor`。
- Task 4 的分析 API 从投影后的仓储读取结果。

- [ ] **Step 1: 为投影校验、幂等和溯源编写失败测试**

在 `backend/tests/analysis/test_projector.py` 使用内存引用仓储、分析仓储和
`qualified_payload()`，覆盖：

```python
projected = await projector.project(definition, run)
replayed = await projector.project(definition, run)

assert projected is not None
assert replayed is not None
assert replayed.id == projected.id
assert projected.reference_id == UUID(run.trigger["reference_id"])
assert projected.reference_revision == int(run.trigger["revision"])
assert projected.source_name == "Example Engineering"
assert projected.provenance["screening"]["agent_version"] == 1
assert projected.provenance["analysis"]["agent_version"] == 2
```

另行覆盖：

- 工作流未声明 projection 时返回 `None`；
- trigger 引用与输出引用不一致；
- trigger 修订与输出修订不一致；
- 修订不存在；
- 输出包含瞬态文档；
- 输出不符合状态 Schema；
- 同一业务标识来自不同 run 时返回已存在分析；
- projection 失败时不写入分析仓储。

- [ ] **Step 2: 运行投影测试并确认失败**

Run:

```bash
cd backend
../.venv/bin/pytest tests/analysis/test_projector.py -q
```

Expected: FAIL with missing `zeromind.analysis.projector`。

- [ ] **Step 3: 实现 `AnalysisProjector`**

构造函数和公开方法固定为：

```python
class AnalysisProjector:
    def __init__(
        self,
        analysis_repository: AnalysisRepository,
        reference_repository: ReferenceRepository,
        subscription_repository: SubscriptionRepository,
    ) -> None:
        self._analyses = analysis_repository
        self._references = reference_repository
        self._subscriptions = subscription_repository

    async def project(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> ContentAnalysis | None:
```

方法执行顺序：

1. `definition.spec.projection is None` 时返回 `None`；
2. 只接受 `content_analysis_v1`；
3. 先按 run ID、再按业务唯一标识查重；
4. 使用 `ContentAnalysisDraftV1.model_validate(run.output)`；
5. 校验 trigger、draft、引用仓储三方的引用与修订一致；
6. 读取 `draft.reference.subscription_id` 对应的 Subscription，并把标题和 Feed URL
   固化为 `source_name` 与 `source_feed_url`；
7. 把 screening/content 中 `_execution` 转成 provenance；
8. 用验证后的 draft 创建 `ContentAnalysis`；
9. 调用仓储 `add`；
10. 并发唯一约束冲突时读取并返回已存在聚合。

- [ ] **Step 4: 为统一运行服务编写失败测试**

创建 `backend/tests/workflows/test_service.py`：

```python
@pytest.mark.asyncio
async def test_service_projects_completed_run_once() -> None:
    run = await service.execute(
        definition.id,
        trigger={
            "event": "manual",
            "reference_id": str(reference.id),
            "revision": 1,
        },
        idempotency_key="manual:analysis-1",
    )

    assert run.status == "completed"
    assert len(await analyses.list(AnalysisQuery(effective_decision=None))) == 1
```

增加 projection 校验失败测试，断言：

```python
assert stored.status == "failed"
assert stored.error is not None
assert "analysis_projection_invalid" in stored.error
assert await analyses.get_by_run(stored.id) is None
```

- [ ] **Step 5: 实现 `WorkflowRunService` 和运行失败标记**

在 `WorkflowRun` 增加：

```python
def fail_projection(self, message: str, *, now: datetime | None = None) -> None:
    self.status = "failed"
    self.error = f"analysis_projection_invalid: {message}"
    self.completed_at = now or datetime.now(UTC)
```

创建 `backend/src/zeromind/workflows/service.py`：

```python
class WorkflowResultProjector(Protocol):
    async def project(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> object | None: ...


class WorkflowRunService:
    def __init__(
        self,
        repository: WorkflowRepository,
        executor: WorkflowExecutor,
        projectors: dict[str, WorkflowResultProjector],
    ) -> None:
        self._repository = repository
        self._executor = executor
        self._projectors = projectors

    async def execute(
        self,
        definition_id: uuid.UUID,
        *,
        trigger: dict[str, object],
        idempotency_key: str,
    ) -> WorkflowRun:
        definition = await self._repository.get_definition(definition_id)
        if definition is None:
            raise KeyError(definition_id)
        run = await self._executor.execute(
            definition_id,
            trigger=trigger,
            idempotency_key=idempotency_key,
        )
        projection = definition.spec.projection
        if projection is None:
            return run
        projector = self._projectors[projection]
        try:
            await projector.project(definition, run)
        except Exception as error:
            run.fail_projection(str(error))
            await self._repository.save_run(run)
            raise ValueError(run.error) from error
        return run
```

- [ ] **Step 6: 将 API 和 Worker 切换到统一服务**

`create_workflow_router` 第二个参数改为 `WorkflowRunService`。手工运行端点调用
`service.execute`。

`create_app` 增加可注入的 `analysis_repository` 和 `workflow_run_service`，默认使用
SQLAlchemy 分析仓储和 `AnalysisProjector` 构建服务。

`_dispatch_outbox` 同样构建服务，事件处理器调用服务后才写
`workflow.completed` outbox。投影失败时不能投递成功 webhook。

更新现有 API 和调度测试中的构造参数，保留非投影工作流原有行为。

- [ ] **Step 7: 运行投影、工作流 API 和调度测试**

Run:

```bash
cd backend
../.venv/bin/pytest \
  tests/analysis/test_projector.py \
  tests/workflows/test_service.py \
  tests/workflows/test_api.py \
  tests/integration/test_schedule.py -q
../.venv/bin/ruff check src tests/analysis tests/workflows
../.venv/bin/mypy src
```

Expected: 全部 PASS。

- [ ] **Step 8: 提交结果投影**

```bash
git add \
  backend/src/zeromind/analysis/projector.py \
  backend/src/zeromind/workflows/service.py \
  backend/src/zeromind/workflows/domain.py \
  backend/src/zeromind/workflows/api.py \
  backend/src/zeromind/bootstrap/app.py \
  backend/src/zeromind/bootstrap/tasks.py \
  backend/tests/analysis/test_projector.py \
  backend/tests/workflows/test_service.py \
  backend/tests/workflows/test_api.py \
  backend/tests/integration/test_schedule.py
git commit -m "feat: project workflow results into analyses"
```

---

### Task 4: 分析信息流 API 与人工改判

**Files:**

- Create: `backend/src/zeromind/analysis/service.py`
- Create: `backend/src/zeromind/analysis/api.py`
- Create: `backend/src/zeromind/identity/context.py`
- Modify: `backend/src/zeromind/bootstrap/app.py`
- Modify: `backend/src/zeromind/identity/api.py`
- Test: `backend/tests/analysis/test_service.py`
- Test: `backend/tests/analysis/test_api.py`
- Test: `backend/tests/identity/test_api.py`

**Interfaces:**

- Produces `request_identity(request: Request) -> AdminIdentity`.
- Produces `AnalysisService.list`, `get`, `override`.
- Produces `GET /api/v1/analyses`, `GET /api/v1/analyses/{id}` 和
  `POST /api/v1/analyses/{id}/overrides`。
- Task 6 frontend consumes the response types defined here.

- [ ] **Step 1: 为请求身份上下文编写失败测试**

更新 identity API 测试，断言生产鉴权中间件通过验证后：

```python
@app.get("/identity-probe")
def identity_probe(request: Request) -> dict[str, str]:
    identity = request_identity(request)
    return {"username": identity.username, "role": identity.role}
```

合法 Bearer token 返回 `{"username": "admin", "role": "admin"}`；缺少身份时
`request_identity` 抛出 401 `authentication_required`。

- [ ] **Step 2: 实现共享请求身份**

创建 `backend/src/zeromind/identity/context.py`：

```python
def request_identity(request: Request) -> AdminIdentity:
    identity = getattr(request.state, "identity", None)
    if not isinstance(identity, AdminIdentity):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required"},
        )
    return identity
```

在 `authenticate_admin_api` 中验证成功后执行：

```python
request.state.identity = resolved_token_service.verify(token)
```

`/api/v1/auth/me` 改为复用相同 `AdminIdentity` 类型和校验逻辑，不创建第二份身份状态。

- [ ] **Step 3: 为查询、游标和改判服务编写失败测试**

在 `backend/tests/analysis/test_service.py` 覆盖：

- 默认只列 `effective_decision=qualified`；
- `include_rejected` 显式返回拒绝项；
- minimum score、分类、标签、订阅源、引用和日期范围；
- limit 只能为 1 到 100；
- 游标使用 URL-safe base64 编码 `(sort_score, content_time, id)`；
- 错误游标返回稳定 `invalid_cursor`；
- 改判追加 sequence、要求理由和 actor；
- 找不到分析返回 `KeyError`。

游标往返断言：

```python
cursor = encode_cursor(86, content_time, analysis_id)
assert decode_cursor(cursor) == (86, content_time, analysis_id)
```

- [ ] **Step 4: 实现分析应用服务**

在 `backend/src/zeromind/analysis/service.py` 定义：

```python
@dataclass(frozen=True, slots=True)
class AnalysisPage:
    items: tuple[ContentAnalysis, ...]
    next_cursor: str | None


class AnalysisService:
    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository

    # list、get 和 override 按下面的确定性规则实现。
```

`list(query)` 请求 `limit + 1` 条，只返回前 `limit` 条；超出时用最后一个已返回项
的 `(total_score or -1, content_time, id)` 生成 next cursor。`get(analysis_id)`
找不到时抛出 `KeyError`。`override(...)` 读取现有聚合，调用领域方法创建下一条
记录，再调用仓储事务方法；返回仓储重新加载后的聚合。

- [ ] **Step 5: 为 REST 契约编写失败测试**

在 `backend/tests/analysis/test_api.py` 通过注入内存仓储构建 app，测试：

```python
listed = client.get("/api/v1/analyses?minimum_score=80")
detail = client.get(f"/api/v1/analyses/{analysis.id}")
overridden = client.post(
    f"/api/v1/analyses/{analysis.id}/overrides",
    headers={"authorization": f"Bearer {token}"},
    json={
        "decision": "rejected",
        "reason": "Manual review found unsupported claims.",
    },
)

assert listed.status_code == 200
assert listed.json()["items"][0]["title"] == "A useful article"
assert listed.json()["items"][0]["source_name"] == "Example Engineering"
assert detail.json()["dimensions"][0]["name"] == "depth"
assert overridden.json()["effective_decision"] == "rejected"
assert overridden.json()["overrides"][-1]["actor_subject"] == "admin"
assert "ARTICLE BODY" not in listed.text + detail.text
```

同时覆盖 404、无身份改判 401、短理由 422、无效 decision 422 和错误游标 422。

- [ ] **Step 6: 实现分析 API**

响应模型分为：

- `AnalysisCardResponse`：卡片字段；
- `AnalysisDetailResponse`：摘要、观点、金句、维度、筛选、溯源和改判历史；
- `AnalysisListResponse`：`items` 和 `next_cursor`；
- `CreateOverrideRequest`：decision 与 reason。

`GET /api/v1/analyses` 显式接收并校验 `generated_status`、
`effective_decision`、`minimum_score`、`category`、`tag`、`subscription_id`、
`reference_id`、`observed_from`、`observed_to`、`limit` 和 `cursor`，逐项映射到
`AnalysisQuery`；若要查看自动或人工拒绝项，客户端必须显式传
`effective_decision=rejected`。

所有内部状态在 API 中使用固定字符串：

```text
initial_rejected
fine_rejected
qualified
rejected
```

在 `create_app` 中构建 `AnalysisService` 并注册 router。生产中间件继续保护整个
`/api/v1`，改判端点额外使用 `request_identity` 取得 actor。

- [ ] **Step 7: 运行分析 API 与身份测试**

Run:

```bash
cd backend
../.venv/bin/pytest tests/analysis/test_service.py tests/analysis/test_api.py tests/identity -q
../.venv/bin/ruff check src/zeromind/analysis src/zeromind/identity tests/analysis tests/identity
../.venv/bin/mypy src
```

Expected: 全部 PASS。

- [ ] **Step 8: 提交分析 API 和改判**

```bash
git add \
  backend/src/zeromind/analysis/service.py \
  backend/src/zeromind/analysis/api.py \
  backend/src/zeromind/identity/context.py \
  backend/src/zeromind/identity/api.py \
  backend/src/zeromind/bootstrap/app.py \
  backend/tests/analysis/test_service.py \
  backend/tests/analysis/test_api.py \
  backend/tests/identity
git commit -m "feat: expose analysis feed and decision overrides"
```

---

### Task 5: 归属明确的用户笔记

**Files:**

- Create: `backend/src/zeromind/notes/__init__.py`
- Create: `backend/src/zeromind/notes/domain.py`
- Create: `backend/src/zeromind/notes/models.py`
- Create: `backend/src/zeromind/notes/repository.py`
- Create: `backend/src/zeromind/notes/service.py`
- Create: `backend/src/zeromind/notes/api.py`
- Create: `backend/migrations/versions/0009_notes.py`
- Modify: `backend/src/zeromind/bootstrap/app.py`
- Modify: `backend/src/zeromind/analysis/api.py`
- Test: `backend/tests/notes/test_domain.py`
- Test: `backend/tests/notes/test_repository.py`
- Test: `backend/tests/notes/test_service.py`
- Test: `backend/tests/notes/test_api.py`
- Test: `backend/tests/analysis/test_api.py`

**Interfaces:**

- Produces `Note` aggregate and `NoteRepository`.
- Produces `GET /api/v1/notes`、`POST /api/v1/notes`、
  `PUT /api/v1/notes/{id}`、`DELETE /api/v1/notes/{id}`。
- Task 7 frontend consumes these endpoints.

- [ ] **Step 1: 为笔记领域约束编写失败测试**

创建 `backend/tests/notes/test_domain.py`，覆盖：

```python
def test_note_normalizes_body_and_updates_timestamp() -> None:
    note = Note.create(
        reference_id=REFERENCE_ID,
        analysis_id=ANALYSIS_ID,
        owner_subject="admin",
        body="  Important insight  ",
        now=NOW,
    )
    note.update(body="Updated insight", analysis_id=None, now=LATER)

    assert note.body == "Updated insight"
    assert note.analysis_id is None
    assert note.updated_at == LATER
```

另行覆盖空正文、只含空白、UTF-8 编码后超过 65,536 字节、空 owner subject。

- [ ] **Step 2: 实现 `Note` 聚合**

`backend/src/zeromind/notes/domain.py`：

```python
MAX_NOTE_BYTES = 65_536


@dataclass(slots=True)
class Note:
    id: uuid.UUID
    reference_id: uuid.UUID
    analysis_id: uuid.UUID | None
    owner_subject: str
    body: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def normalize_body(value: str) -> str:
        body = value.strip()
        if not body:
            raise ValueError("note body is required")
        if len(body.encode("utf-8")) > MAX_NOTE_BYTES:
            raise ValueError("note body exceeds 65536 UTF-8 bytes")
        return body
```

`create` 和 `update` 都必须复用 `normalize_body`。

- [ ] **Step 3: 为笔记仓储编写失败测试**

仓储测试覆盖：

- 完整往返；
- 按 owner、reference、analysis 过滤；
- owner 不匹配时 `get_owned` 返回 `None`；
- 更新只影响目标笔记；
- 硬删除后查询为空。

- [ ] **Step 4: 创建笔记模型、迁移和仓储**

`NoteModel` 字段：

```python
id
reference_id
analysis_id
owner_subject
body
created_at
updated_at
```

`reference_id` 外键指向 `content_references.id` 并使用 `ON DELETE CASCADE`；
`analysis_id` 可空外键指向 `content_analyses.id` 并使用 `ON DELETE SET NULL`；
为 `(owner_subject, reference_id)` 和 `(owner_subject, analysis_id)` 建索引。

迁移 `0009_notes.py` 的 `down_revision` 为 `0008_content_analyses`。

仓储协议：

```python
class NoteRepository(Protocol):
    async def add(self, note: Note) -> None: ...
    async def get_owned(
        self,
        note_id: uuid.UUID,
        owner_subject: str,
    ) -> Note | None: ...
    async def list_owned(
        self,
        owner_subject: str,
        *,
        reference_id: uuid.UUID | None = None,
        analysis_id: uuid.UUID | None = None,
    ) -> tuple[Note, ...]: ...
    async def save(self, note: Note) -> None: ...
    async def delete(self, note_id: uuid.UUID, owner_subject: str) -> None: ...
```

- [ ] **Step 5: 为应用服务的跨引用校验编写失败测试**

测试创建和更新时：

- reference 必须存在；
- analysis 存在时必须属于同一 reference；
- 修改他人笔记返回 `KeyError`；
- 删除他人笔记返回 `KeyError`；
- 笔记写入不会改变分析对象。

- [ ] **Step 6: 实现 `NoteService`**

构造函数：

```python
class NoteService:
    def __init__(
        self,
        notes: NoteRepository,
        references: ReferenceRepository,
        analyses: AnalysisRepository,
    ) -> None:
        self._notes = notes
        self._references = references
        self._analyses = analyses
```

公开方法为 `list_owned`、`create`、`update`、`delete`。创建或更新可选
`analysis_id` 时读取分析并比较 `analysis.reference_id == reference_id`。

- [ ] **Step 7: 为笔记 API 编写失败测试**

使用真实测试 token 发送：

```python
created = client.post(
    "/api/v1/notes",
    headers={"authorization": f"Bearer {token}"},
    json={
        "reference_id": str(reference.id),
        "analysis_id": str(analysis.id),
        "body": "重点关注确定性评分。",
    },
)
listed = client.get(
    f"/api/v1/notes?reference_id={reference.id}",
    headers={"authorization": f"Bearer {token}"},
)

assert created.status_code == 201
assert created.json()["owner_subject"] == "admin"
assert listed.json()["items"] == [created.json()]
```

请求体提交 `owner_subject` 必须被 Pydantic 拒绝。另行覆盖更新、删除、未登录 401、
跨引用 422、空正文 422、过长正文 422 和非所有者 404。

- [ ] **Step 8: 实现笔记 API 并注册路由**

所有端点首先调用 `request_identity(request)`，请求模型使用
`ConfigDict(extra="forbid")`，不能接收 owner。删除返回 204。

`create_app` 增加可注入 `note_repository`，默认创建 SQLAlchemy 仓储和
`NoteService`。

同时把 `NoteService` 注入分析 router，使 `GET /api/v1/analyses/{id}` 的
`notes` 字段返回当前身份在该引用下的笔记。未提供有效身份时只允许在测试模式下返回
空列表；生产中整个 `/api/v1` 已由鉴权中间件保护。增加分析 API 契约测试，断言详情
中的笔记只属于当前 subject，且不包含其他用户笔记。

- [ ] **Step 9: 运行笔记测试、迁移检查和静态检查**

Run:

```bash
cd backend
../.venv/bin/pytest tests/notes tests/analysis/test_api.py -q
../.venv/bin/alembic upgrade head --sql >/tmp/zeromind-notes-migration.sql
../.venv/bin/ruff check src/zeromind/notes tests/notes migrations/versions/0009_notes.py
../.venv/bin/mypy src
```

Expected: 全部 PASS。

- [ ] **Step 10: 提交笔记后端**

```bash
git add \
  backend/src/zeromind/notes \
  backend/src/zeromind/analysis/api.py \
  backend/src/zeromind/bootstrap/app.py \
  backend/migrations/versions/0009_notes.py \
  backend/tests/notes
git commit -m "feat: add owned reading notes"
```

---

### Task 6: 结构化信息流与分析详情前端

**Files:**

- Create: `frontend/src/pages/analyses.tsx`
- Create: `frontend/src/pages/analysis-detail.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/app.tsx`
- Modify: `frontend/src/components.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/app.test.tsx`

**Interfaces:**

- Consumes Task 4 analysis list/detail/override API。
- Produces `/analyses` 信息流和 `/analyses/:analysisId` 详情路由。
- Task 7 在分析详情页插入笔记区域。

- [ ] **Step 1: 定义前端类型并编写信息流失败测试**

在 `frontend/src/api/client.ts` 增加：

```typescript
export type AnalysisCard = {
  id: string;
  reference_id: string;
  source_name: string;
  source_feed_url: string;
  title: string;
  original_url: string | null;
  author: string | null;
  published_at: string | null;
  observed_at: string;
  generated_status: "initial_rejected" | "fine_rejected" | "qualified";
  effective_decision: "qualified" | "rejected";
  primary_category: string | null;
  tags: string[];
  one_sentence_summary: string | null;
  total_score: number | null;
  recommendation_level: string | null;
  recommendation_reason: string | null;
  overridden: boolean;
};
```

在 `frontend/src/app.test.tsx` 增加信息流测试。Mock `/analyses` 返回两张卡片，
断言默认展示：

- 导航“信息流”；
- 标题“A useful article”；
- 来源“Example Engineering”；
- 分数“86”；
- 分类“AI”；
- 一句话摘要；
- “人工改判”标识；
- 原文链接具有 `target="_blank"`；
- 被拒绝视图按钮。

- [ ] **Step 2: 运行前端测试并确认失败**

Run:

```bash
cd frontend
pnpm test -- app.test.tsx
```

Expected: FAIL，找不到“信息流”导航和页面内容。

- [ ] **Step 3: 实现信息流页面**

`AnalysesPage` 使用以下 query key：

```typescript
[
  "analyses",
  {
    effectiveDecision,
    minimumScore,
    category,
    subscriptionId,
    from,
    to
  }
]
```

生成 URL 时只附加非空参数。页面包含：

- “通过内容 / 已拒绝”分段控件；
- 最低分数数字输入；
- 分类文本输入；
- 从 `/api/v1/subscriptions` 加载订阅源下拉框，并把选中的 ID 写入
  `subscription_id` 查询参数；
- 日期起止输入；
- 卡片网格；
- “加载更多”按钮，使用 `next_cursor`；
- 加载、空状态和错误状态。

卡片点击标题进入 `/analyses/{id}`，原文链接单独打开新标签，不能触发详情导航。

- [ ] **Step 4: 为分析详情和人工改判编写失败测试**

Mock 详情响应并断言：

- 摘要；
- 两个观点；
- 六个评分维度及权重；
- 金句；
- 初筛理由；
- 工作流、Agent、Provider 和模型溯源；
- 改判历史。

提交改判表单后断言请求：

```typescript
expect(JSON.parse(String(overrideRequest?.body))).toEqual({
  decision: "rejected",
  reason: "人工复核发现关键论据缺少来源。"
});
```

- [ ] **Step 5: 实现分析详情和改判交互**

`AnalysisDetailPage`：

- query key `["analysis", analysisId]`；
- 改判 mutation 成功后刷新详情和信息流；
- 理由少于 10 个字符时禁用提交；
- 维度显示分值、权重百分比和理由；
- 金句使用 `<blockquote>`；
- 原文使用安全的新标签链接；
- 没有全文阅读器或正文请求。

- [ ] **Step 6: 增加导航、路由、状态中文映射和样式**

路由：

```tsx
<Route path="/analyses" element={<AnalysesPage />} />
<Route path="/analyses/:analysisId" element={<AnalysisDetailPage />} />
```

导航把“信息流”放在“内容引用”之后。增加中文状态映射：

```typescript
const analysisStatusLabels = {
  initial_rejected: "初筛拒绝",
  fine_rejected: "细筛拒绝",
  qualified: "通过",
  rejected: "已拒绝"
} as const;
```

样式必须覆盖桌面卡片、评分维度、详情双栏、窄屏单栏和键盘 focus 状态。

- [ ] **Step 7: 运行前端测试、类型检查和构建**

Run:

```bash
cd frontend
pnpm test
pnpm typecheck
pnpm build
```

Expected: 全部 PASS。

- [ ] **Step 8: 提交信息流前端**

```bash
git add \
  frontend/src/pages/analyses.tsx \
  frontend/src/pages/analysis-detail.tsx \
  frontend/src/api/client.ts \
  frontend/src/app.tsx \
  frontend/src/components.tsx \
  frontend/src/styles.css \
  frontend/src/app.test.tsx
git commit -m "feat: add structured information flow UI"
```

---

### Task 7: 分析详情中的用户笔记

**Files:**

- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/analysis-detail.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/app.test.tsx`

**Interfaces:**

- Consumes Task 5 notes API。
- Produces分析详情页内的笔记创建、编辑和删除闭环。

- [ ] **Step 1: 定义 Note 类型并编写失败测试**

在 client 类型中增加：

```typescript
export type Note = {
  id: string;
  reference_id: string;
  analysis_id: string | null;
  owner_subject: string;
  body: string;
  created_at: string;
  updated_at: string;
};
```

前端测试覆盖：

1. 详情加载后请求 `/notes?reference_id=...`；
2. 空状态显示“还没有笔记”；
3. 输入 Markdown 并创建；
4. 点击编辑，保存新正文；
5. 点击删除后从列表移除；
6. API 错误显示在笔记区域，不隐藏分析内容。

创建请求断言：

```typescript
expect(notePayload).toEqual({
  reference_id: "11111111-1111-1111-1111-111111111111",
  analysis_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  body: "这条评分规则可以用于项目评审。"
});
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
cd frontend
pnpm test -- app.test.tsx
```

Expected: FAIL，页面没有笔记编辑器和 CRUD 请求。

- [ ] **Step 3: 实现笔记查询和 CRUD**

使用 query key：

```typescript
["notes", {referenceId: analysis.reference_id}]
```

创建、更新、删除 mutation 成功后只刷新该引用的 notes query。编辑器规则：

- `textarea` 标签为“笔记正文”；
- 空白正文不允许提交；
- 显示 UTF-8 近似字节计数提示；
- 更新时保留 reference ID，可选择保持或清除 analysis ID；
- 删除按钮包含笔记创建时间，避免无障碍名称重复。

- [ ] **Step 4: 完善笔记样式和窄屏行为**

增加 `.notes-panel`、`.note-card`、`.note-editor`。长 Markdown 正文使用
`white-space: pre-wrap` 和 `overflow-wrap: anywhere`，不能注入原始 HTML。

- [ ] **Step 5: 运行前端完整验证**

Run:

```bash
cd frontend
pnpm test
pnpm typecheck
pnpm build
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交笔记前端**

```bash
git add \
  frontend/src/api/client.ts \
  frontend/src/pages/analysis-detail.tsx \
  frontend/src/styles.css \
  frontend/src/app.test.tsx
git commit -m "feat: add reading notes to analysis details"
```

---

### Task 8: 默认工作流示例、端到端验证和容器验收

**Files:**

- Modify: `docs/examples/article-analysis.yaml`
- Create: `docs/examples/screening-agent.json`
- Create: `docs/examples/analysis-agent.json`
- Modify: `README.md`
- Modify: `docs/operations.md`
- Modify: `backend/tests/e2e/test_information_flow.py`
- Modify: `frontend/src/pages/workflows.tsx`
- Test: `backend/tests/e2e/test_information_flow.py`

**Interfaces:**

- Produces可复制的初筛 Agent、深度分析 Agent 和完整工作流配置。
- Produces覆盖初筛拒绝、细筛拒绝、通过、人工改判、笔记和正文不落库的端到端证据。
- 不引入真实 Provider 或公共 RSSHub 依赖。

- [ ] **Step 1: 扩展端到端测试并确认失败**

将现有 e2e fixture 扩展为三条引用，Fake Pi 根据输入标题返回固定结果：

```python
RESULTS = {
    "Noise": {
        "score": 10,
        "reason": "Announcement without substantive content",
        "summary": "Low-value announcement",
    },
    "Average": {
        "score": 75,
        "reason": "Potentially useful",
        "summary": "Potentially useful article",
    },
    "Excellent": {
        "score": 95,
        "reason": "High-value technical content",
        "summary": "High-value article",
    },
}
```

深度分析阶段让 Average 的确定性总分为 60，Excellent 为 90。测试断言：

```python
assert statuses == ["initial_rejected", "fine_rejected", "qualified"]
assert fake_pi.full_content_calls == 2
assert "ARTICLE BODY MUST NOT BE STORED" not in persisted_database_dump
assert overridden.effective_decision == "qualified"
assert created_note.reference_id == average_reference.id
```

- [ ] **Step 2: 运行 e2e 测试并确认失败**

Run:

```bash
cd backend
../.venv/bin/pytest tests/e2e/test_information_flow.py -q
```

Expected: FAIL，因为完整分析工作流、投影、改判和笔记链路尚未全部接入 fixture。

- [ ] **Step 3: 编写可用的 Agent 配置示例**

`screening-agent.json` 必须包含：

- capability `screen-content`；
- 输入 Schema 要求 `metadata` 和 `audience`；
- 输出 Schema 严格要求 `score`、`reason`、`summary`；
- system prompt 只使用 RSS 元数据判断相关性、实质性和初步价值；
- 明确不能声称读过全文。

`analysis-agent.json` 必须包含：

- capability `analyze-content`；
- 输入 Schema 要求 `metadata`、`document`、`audience`；
- 输出 Schema 严格匹配分类、摘要、观点、金句、六个维度分值和理由、推荐信息；
- 金句数量和长度约束；
- 明确只能从传入文档提取事实和原句。

示例中 `provider_profile_id` 使用固定无效 UUID，并在 README 明确要求替换。

- [ ] **Step 4: 更新完整 YAML 工作流示例**

把 `docs/examples/article-analysis.yaml` 替换为已确认设计中的
`reference → screen → initial_gate → resolve → analyze → score → fine_gate`
流程，包含：

- `projection: content_analysis_v1`；
- 初筛阈值 30；
- 六维权重；
- 细筛阈值 70；
- 两种拒绝输出和通过输出；
- 两个清晰标注需替换的 Agent UUID。

`frontend/src/pages/workflows.tsx` 的编辑器 placeholder 使用同一精简示例，不能继续只展示 `resolve`。

扩展前端工作流校验响应类型并展示：

```typescript
type WorkflowValidation = {
  name: string;
  topological_order: string[];
  projection: string | null;
  terminal_gates: string[];
  warnings: string[];
};
```

在 `frontend/src/app.test.tsx` 增加契约测试，mock 返回
`projection: "content_analysis_v1"`、两个 terminal gates 和一条 warning，断言页面
显示投影名称、`initial_gate`、`fine_gate` 和警告内容。

- [ ] **Step 5: 更新 README 和运维文档**

README 增加：

- `analysis` 与 `notes` 限界上下文；
- 创建 Provider、两个 Agent、替换 UUID、校验和激活工作流的准确顺序；
- 信息流、拒绝审计、人工改判和笔记使用说明；
- 原文不落库与金句上限。

运维文档增加：

- 0008/0009 迁移和回滚表；
- Agent Schema mismatch、projection invalid、门禁类型错误排查；
- 观察初筛通过率、细筛通过率、模型调用节省比例和人工改判率；
- Provider 不可用时不会产生部分分析；
- 备份必须包含 analyses、tags、overrides、notes 表。

- [ ] **Step 6: 运行完整后端验证**

Run:

```bash
cd backend
../.venv/bin/pytest -q
../.venv/bin/ruff check src tests migrations
../.venv/bin/mypy src
```

Expected: 全部 PASS。

- [ ] **Step 7: 运行 Pi Runner 和前端验证**

Run:

```bash
cd pi-runner
pnpm test
pnpm typecheck
pnpm build

cd ../frontend
pnpm test
pnpm typecheck
pnpm build
```

Expected: 全部 PASS。

- [ ] **Step 8: 重建容器并验证迁移与健康状态**

Run:

```bash
docker compose up --build -d
docker compose ps
docker compose exec -T api python -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health/live').read().decode())"
docker compose exec -T postgres psql -U zeromind -d zeromind -Atc \
  "select version_num from alembic_version"
```

Expected:

- `api`、`worker`、`scheduler`、`postgres`、`redis` 和 `frontend` 均为运行状态；
- live health 返回 `{"status":"ok"}`；
- Alembic 版本为 `0009_notes`。

- [ ] **Step 9: 执行浏览器验收**

在 `http://localhost:8080` 验证：

1. 登录成功；
2. 导航显示“信息流”；
3. 空数据时显示明确空状态；
4. 工作流编辑器显示新的 DSL 示例；
5. 使用 API fixture 或测试数据库插入三种分析状态后，信息流过滤正确；
6. 详情页显示摘要、观点、评分、金句和溯源；
7. 人工改判后列表状态更新；
8. 笔记创建、编辑、删除生效；
9. 窄屏布局无横向溢出；
10. 网络请求中没有正文持久化接口。

- [ ] **Step 10: 检查提交范围和文档一致性**

Run:

```bash
git status --short
git log --oneline -12
rg -n "TO""DO|TB""D|FIX""ME" \
  README.md \
  docs/examples \
  docs/operations.md \
  backend/src/zeromind/analysis \
  backend/src/zeromind/notes \
  frontend/src/pages
```

Expected:

- 仅剩用户原有的三个无关迁移启动改动；
- 提交历史包含本计划规定的独立功能提交；
- 搜索无输出。

- [ ] **Step 11: 提交文档与端到端验收**

```bash
git add \
  README.md \
  docs/examples/article-analysis.yaml \
  docs/examples/screening-agent.json \
  docs/examples/analysis-agent.json \
  docs/operations.md \
  backend/tests/e2e/test_information_flow.py \
  frontend/src/pages/workflows.tsx \
  frontend/src/app.test.tsx
git commit -m "docs: document and verify the analysis workflow"
```

---

## 完成审计清单

实施结束前逐项提供证据：

- [ ] RSS 元数据初筛不会读取原文。
- [ ] 初筛拒绝不会调用全文分析 Agent。
- [ ] 全文只在运行期存在，数据库、步骤、日志和 outbox 中没有正文。
- [ ] 分类、摘要、观点、金句和各维度评分均来自通过 Schema 校验的 Agent 输出。
- [ ] 总分由 `score` 节点确定性计算。
- [ ] 细筛门禁使用 DSL 阈值并可提前终止。
- [ ] 三种生成状态都投影为幂等的 `ContentAnalysis`。
- [ ] 默认信息流只展示有效结论为 qualified 的内容。
- [ ] 人工改判追加审计记录，不覆盖 Agent 结果和分数。
- [ ] 用户可以创建、修改、查询和删除自己的笔记。
- [ ] API 和 UI 不返回解析出的完整正文。
- [ ] 后端、Pi Runner、前端、迁移、容器和浏览器验收全部通过。
- [ ] 每个功能提交只包含其职责内文件。

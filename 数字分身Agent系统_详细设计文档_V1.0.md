# 数字分身Agent系统 — 深度详细设计文档

> **版本**: V1.1  
> **日期**: 2026-05-20  
> **基于**: 数字分身Agent系统_PRD_V1.0

---

## 目录

1. [Master Agent 深度设计](#一master-agent-深度设计)
2. [知识图谱 Schema 设计](#二知识图谱-schema-设计)
3. [Agent 通信与协作协议](#三agent-通信与协作协议)
4. [API 接口设计](#四api-接口设计)
5. [数据模型设计](#五数据模型设计)
6. [部署架构设计](#六部署架构设计)
7. [安全与合规设计](#七安全与合规设计)

---

## 一、Master Agent 深度设计

### 1.1 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│                    Master Agent 架构                         │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: 输出层 (Output Layer)                              │
│  ├─ Response Synthesizer（响应合成器）                       │
│  ├─ Quality Validator（质量验证器）                          │
│  └─ Self-Correction Loop（自纠正循环）                       │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: 协调层 (Coordination Layer)                        │
│  ├─ Agent Orchestrator（Agent编排器）                        │
│  ├─ Conflict Resolver（冲突解决器）                          │
│  └─ Parallel Executor（并行执行器）                          │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: 决策层 (Decision Layer)                            │
│  ├─ Intent Classifier（意图分类器）                        │
│  ├─ Task Decomposer（任务分解器）                            │
│  └─ Agent Router（Agent路由器）                              │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: 输入层 (Input Layer)                               │
│  ├─ Query Preprocessor（查询预处理器）                       │
│  ├─ Context Enricher（上下文增强器）                         │
│  └─ Memory Retriever（记忆检索器）                           │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 意图分类器设计

#### 1.2.1 意图分类体系

采用三级分类体系：
- **Level 1**: 领域 (Domain) - 8大类
- **Level 2**: 意图 (Intent) - 32小类  
- **Level 3**: 槽位 (Slot) - 动态提取

| 领域 | 意图 | 触发关键词 | 调度Agent |
|------|------|-----------|-----------|
| **product** | product_search | 产品检索、型号查询 | 产品专家 |
| **product** | product_comparison | 产品对比、竞品对比 | 产品专家 |
| **product** | inventory_query | 库存查询、现货查询 | 产品专家 |
| **product** | pricing_query | 价格查询、报价 | 产品专家 |
| **customer** | customer_profile | 客户画像、客户信息 | 客户专家 |
| **customer** | background_research | 客户背调、企业调查 | 客户专家 |
| **customer** | follow_up | 跟进策略、客户没回 | 客户专家 |
| **lead** | lead_scoring | 线索评分、线索质量 | 线索专家 |
| **lead** | lead_assignment | 线索分配、谁跟这个线索 | 线索专家 |
| **opportunity** | opportunity_assessment | 商机评估、赢率预测 | 商机专家 |
| **opportunity** | opportunity_strategy | 推进策略、下一步 | 商机专家 |
| **opportunity** | risk_warning | 风险预警、丢单风险 | 商机专家 |
| **script** | objection_handling | 异议处理、客户说贵 | 话术专家 |
| **script** | script_polish | 话术润色、怎么说更好 | 话术专家 |
| **script** | email_generation | 写邮件、邮件模板 | 话术专家 |
| **communication** | visit_summary | 拜访总结、会议纪要 | 客户专家+质检专家 |
| **communication** | visit_quality_check | 拜访质检、沟通质检 | 质检专家 |

#### 1.2.2 意图分类算法

```python
class IntentClassifier:
    def classify(self, query: str, context: dict) -> IntentResult:
        # Step 1: 规则快速匹配
        rule_result = self.rule_engine.match(query)
        if rule_result.confidence > 0.9:
            return rule_result

        # Step 2: 语义编码（向量相似度）
        semantic_result = self.semantic_model.encode_and_match(query)

        # Step 3: 上下文感知重排序
        ranked_result = self.context_aware.rerank(
            candidates=[rule_result, semantic_result],
            context=context
        )

        # Step 4: 置信度判断
        if ranked_result.confidence < 0.75:
            return self._clarify_intent(query, ranked_result)

        return ranked_result
```

#### 1.2.3 槽位提取

```python
def _extract_slots(self, query: str, intent: str) -> dict:
    slots = {}
    slots["product_model"] = self._extract_product_model(query)
    slots["product_category"] = self._extract_product_category(query)
    slots["customer_name"] = self._extract_customer_name(query)
    slots["customer_industry"] = self._extract_industry(query)
    slots["time_range"] = self._extract_time(query)
    slots["price_range"] = self._extract_price(query)
    slots["competitor"] = self._extract_competitor(query)
    return slots
```

### 1.3 任务分解器设计

```python
class TaskDecomposer:
    def decompose(self, intent: IntentResult, context: dict) -> TaskGraph:
        task_graph = TaskGraph()
        template = self._get_template(intent)
        filled_template = self._fill_template(template, intent.slots, context)

        for task_def in filled_template.tasks:
            task = Task(
                id=generate_uuid(),
                agent_type=task_def.agent_type,
                action=task_def.action,
                input_params=task_def.params,
                output_schema=task_def.expected_output,
                timeout_ms=task_def.timeout,
                retry_policy=task_def.retry
            )
            task_graph.add_node(task)

        for dep in filled_template.dependencies:
            task_graph.add_edge(
                from_task=dep.source,
                to_task=dep.target,
                condition=dep.condition,
                data_mapping=dep.mapping
            )

        return task_graph
```

#### 1.3.1 任务模板示例

**价格异议处理模板**：

```
并行阶段：
  1. 产品专家 -> get_product_info (获取产品参数)
  2. 产品专家 -> get_competitor_comparison (获取竞品对比)
  3. 客户专家 -> get_customer_profile (获取客户画像)

串行阶段：
  4. 话术专家 -> generate_objection_response (生成异议回复)
     依赖：1, 2, 3 的输出

监督阶段：
  5. 质检专家 -> validate_response (验证回复质量)
     依赖：4 的输出
```

**客户背调模板**：

```
并行阶段：
  1. 客户专家 -> search_web_info (搜索网络信息)
  2. 客户专家 -> analyze_decision_makers (分析决策人)
  3. 产品专家 -> check_purchase_history (查询购买历史)

串行阶段：
  4. 客户专家 -> generate_profile_report (生成画像报告)
     依赖：1, 2, 3 的输出
```

### 1.4 Agent路由器设计

```python
class AgentRouter:
    def route(self, task: Task) -> AgentInstance:
        # 1. 获取候选Agent列表
        candidates = self.agent_registry.find_by_capability(
            agent_type=task.agent_type,
            required_skills=task.required_skills
        )

        # 2. 过滤不可用Agent
        available = [
            agent for agent in candidates
            if self.circuit_breaker.is_available(agent.id)
        ]

        # 3. 计算综合评分
        scored_agents = []
        for agent in available:
            score = self._calculate_score(agent, task)
            scored_agents.append((agent, score))

        # 4. 选择最优Agent
        scored_agents.sort(key=lambda x: x[1], reverse=True)
        selected = scored_agents[0][0]

        return selected

    def _calculate_score(self, agent: AgentInstance, task: Task) -> float:
        scores = {
            "capability": self._capability_score(agent, task) * 0.4,
            "load": self._load_score(agent) * 0.25,
            "history": self._history_score(agent) * 0.2,
            "affinity": self._affinity_score(agent, task) * 0.15
        }
        return sum(scores.values())
```

### 1.5 冲突解决器设计

```python
class ConflictResolver:
    RESOLUTION_STRATEGIES = {
        "fact_conflict": "evidence_based",
        "opinion_conflict": "confidence",
        "data_conflict": "source_authority",
        "strategy_conflict": "risk_minimal",
    }

    def resolve(self, agent_outputs: list, conflict_type: str) -> ResolvedOutput:
        strategy = self.RESOLUTION_STRATEGIES.get(conflict_type, "default")

        if strategy == "evidence_based":
            return self._evidence_based_resolution(agent_outputs)
        elif strategy == "confidence":
            return self._confidence_based_resolution(agent_outputs)
        elif strategy == "source_authority":
            return self._authority_based_resolution(agent_outputs)
        elif strategy == "risk_minimal":
            return self._risk_minimal_resolution(agent_outputs)
        else:
            return self._default_resolution(agent_outputs)
```

---

## 二、知识图谱 Schema 设计

### 2.1 总体Schema架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                     知识图谱 Schema 总览                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐                   │
│   │  Product |<--->| Scenario |<--->| Industry |                   │
│   │  产品    │    │  场景    │    │  行业    │                   │
│   └────┬─────┘    └────┬─────┘    └────┬─────┘                   │
│        │               │               │                             │
│        ▼               ▼               ▼                             │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐                   │
│   │   Part   |<--->|  Case    |<--->| Customer |                   │
│   │  配件    │    │  案例    │    │  客户    │                   │
│   └────┬─────┘    └────┬─────┘    └────┬─────┘                   │
│        │               │               │                             │
│        ▼               ▼               ▼                             │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐                   │
│   │Competitor|<--->│  Sales   |<--->│  Order   |                   │
│   │  竞品    │    │  销售    │    │  订单    │                   │
│   └──────────┘    └──────────┘    └──────────┘                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 实体（Node）Schema

#### 2.2.1 Product（产品）

| 属性 | 类型 | 说明 | 示例 |
|------|------|------|------|
| id | String | 唯一标识 | PROD_001 |
| model | String | 型号 | VMC-850Pro |
| name | String | 产品名称 | 高刚性立式加工中心 |
| category | String | 产品类别 | 加工中心 |
| sub_category | String | 子类别 | 立式加工中心 |
| brand | String | 品牌 | 磐石 |
| parameters | JSON | 技术参数 | {spindle_speed: "12000rpm"} |
| list_price | Decimal | 指导价 | 285000 |
| cost_price | Decimal | 成本价（内部） | 220000 |
| min_price | Decimal | 底价（内部） | 250000 |
| status | Enum | 状态 | active/discontinued/upcoming |
| stock_qty | Integer | 库存数量 | 5 |
| delivery_days | Integer | 标准交期 | 7 |
| tags | List | 标签 | ["高刚性", "精密加工"] |

#### 2.2.2 Customer（客户）

| 属性 | 类型 | 说明 | 示例 |
|------|------|------|------|
| id | String | 唯一标识 | CUST_001 |
| name | String | 客户名称 | 广州山河科技 |
| industry | String | 行业 | 汽车零部件 |
| scale | String | 规模 | 中型 |
| region | String | 区域 | 华南 |
| company_profile | JSON | 企业画像 | {founded_year: 2010} |
| purchase_behavior | JSON | 采购特征 | {price_sensitivity: "中"} |
| customer_value | JSON | 客户价值 | {total_revenue: 2000000} |
| tags | List | 标签 | ["特斯拉供应商", "高精度需求"] |
| status | Enum | 状态 | active/inactive |

#### 2.2.3 Contact（联系人/决策人）

| 属性 | 类型 | 说明 | 示例 |
|------|------|------|------|
| id | String | 唯一标识 | CONT_001 |
| customer_id | String | 所属客户 | CUST_001 |
| name | String | 姓名 | 王建国 |
| title | String | 职位 | 生产总监 |
| department | String | 部门 | 生产部 |
| decision_role | Enum | 决策角色 | 技术决策者/最终决策者/影响者/使用者 |
| decision_weight | Float | 决策权重 | 0.7 |
| phone | String | 电话 | 138****8888 |
| email | String | 邮箱 | wang@shanhe.com |
| personality | JSON | 个人画像 | {communication_style: "直接高效"} |
| influence_radius | List | 影响范围 | ["CONT_002", "CONT_003"] |

#### 2.2.4 Scenario（应用场景）

| 属性 | 类型 | 说明 | 示例 |
|------|------|------|------|
| id | String | 唯一标识 | SCEN_001 |
| name | String | 场景名称 | 钛合金加工 |
| category | String | 类别 | 材料加工 |
| requirements | JSON | 工艺要求 | {material: "钛合金", hardness: "HRC30-35"} |
| challenges | List | 关键挑战 | ["导热性差", "刀具磨损快"] |
| recommended_solutions | List | 推荐方案 | ["高刚性机床+高压冷却"] |
| required_features | List | 所需产品特征 | ["高刚性", "高压冷却"] |

#### 2.2.5 Case（案例）

| 属性 | 类型 | 说明 | 示例 |
|------|------|------|------|
| id | String | 唯一标识 | CASE_001 |
| name | String | 案例名称 | 特斯拉供应商电机壳体加工 |
| customer_name | String | 客户名称 | XX精密制造 |
| industry | String | 行业 | 新能源汽车 |
| project_info | JSON | 项目信息 | {product_model: "VMC-850Pro", quantity: 6} |
| results | JSON | 效果数据 | {before_quality_rate: "92%", after_quality_rate: "99.8%"} |
| key_factors | List | 关键成功因素 | ["高刚性设计", "12000转主轴"] |
| talking_points | List | 话术要点 | ["良品率从92%提升到99.8%"] |
| applicable_to | List | 适用行业 | ["汽车零部件", "精密模具"] |
| verified | Boolean | 是否已验证 | true |

#### 2.2.6 Competitor（竞品）

| 属性 | 类型 | 说明 | 示例 |
|------|------|------|------|
| id | String | 唯一标识 | COMP_001 |
| brand | String | 品牌 | 日本M牌 |
| model | String | 型号 | M-V500 |
| category | String | 类别 | 立式加工中心 |
| parameters | JSON | 参数 | {spindle_speed: "10000rpm"} |
| list_price | Decimal | 指导价 | 450000 |
| advantages | List | 优势 | ["品牌知名度高"] |
| disadvantages | List | 劣势 | ["价格高60%", "交期长"] |
| counter_strategies | List | 应对策略 | ["强调性价比", "强调现货优势"] |
| market_position | String | 市场定位 | 高端进口 |

### 2.3 关系（Relationship）Schema

| 关系类型 | 起始实体 | 终止实体 | 属性 | 说明 |
|----------|----------|----------|------|------|
| HAS_PART | Product | Part | part_type, is_optional, price | 产品-配件 |
| COMPATIBLE_WITH | Product | Product | compatibility_type, notes | 产品兼容 |
| UPGRADE_TO | Product | Product | upgrade_type, price_difference | 产品升级 |
| SUITABLE_FOR | Product | Scenario | suitability_score, recommended_config | 适用场景 |
| COMPETES_WITH | Product | Competitor | comparison_dimensions, win_rate | 竞品对比 |
| PURCHASED | Customer | Product | order_id, quantity, total_amount | 客户购买 |
| HAS_CONTACT | Customer | Contact | role_in_company, is_primary | 客户联系人 |
| BELONGS_TO | Customer | Industry | segment, tier | 客户行业 |
| FEATURED_IN | Customer | Case | role, testimonial_quote | 客户案例 |
| USES_PRODUCT | Case | Product | quantity, configuration | 案例使用产品 |
| APPLIES_TO | Case | Scenario | relevance_score | 案例适用场景 |
| MANAGES | Sales | Customer | assignment_date, relationship_level | 销售管理客户 |
| OWNS | Sales | Opportunity | ownership_type, commission_rate | 销售拥有商机 |

### 2.4 核心查询模式

```cypher
// Q1: 配件反查 - 客户询问切削液，推荐适配机床
MATCH (fluid:Product {model: "YH-456"})-[:COMPATIBLE_WITH]->(machine:Product)
MATCH (machine)-[:HAS_PART]->(part:Part)
WHERE part.part_type = "标配"
RETURN machine.model AS 推荐机床,
       machine.list_price AS 价格,
       machine.stock_qty AS 库存,
       collect(part.name) AS 标配配件

// Q2: 升级推荐 - 基于客户已购产品推荐升级
MATCH (c:Customer {name: "广州山河科技"})-[:PURCHASED]->(old:Product)
MATCH (old)-[:UPGRADE_TO]->(new:Product)
WHERE new.status = "active"
RETURN old.model AS 现有设备,
       new.model AS 升级推荐,
       new.list_price AS 升级价格

// Q3: 场景案例 - 查找某场景下的成功案例
MATCH (s:Scenario {name: "钛合金加工"})<-[:APPLIES_TO]-(ca:Case)
MATCH (ca)-[:USES_PRODUCT]->(p:Product)
RETURN ca.name AS 案例名称,
       ca.results.after_quality_rate AS 良品率,
       p.model AS 使用产品,
       ca.talking_points AS 话术要点
ORDER BY ca.results.roi_months ASC
LIMIT 3

// Q4: 客户背调 - 生成客户画像报告
MATCH (c:Customer {name: "Tesla Inc"})
OPTIONAL MATCH (c)-[:HAS_CONTACT]->(ct:Contact)
OPTIONAL MATCH (c)-[:PURCHASED]->(p:Product)
OPTIONAL MATCH (c)-[:BELONGS_TO]->(i:Industry)
RETURN c.name AS 客户名称,
       collect(DISTINCT ct { .name, .title, .decision_role }) AS 决策人,
       collect(DISTINCT p.model) AS 已购产品

// Q5: 竞品对比
MATCH (p:Product {model: "VMC-850Pro"})-[r:COMPETES_WITH]->(cp:Competitor)
RETURN p.model AS 我方产品,
       cp.brand + " " + cp.model AS 竞品,
       r.our_advantage AS 我方优势,
       r.win_rate AS 历史赢率

// Q6: 跨产品线搭售推荐
MATCH (c:Customer)-[:PURCHASED]->(p:Product {model: "VMC-850Pro"})
MATCH (p)-[:HAS_PART|COMPATIBLE_WITH*1..2]->(related:Product)
WHERE related.model <> "VMC-850Pro"
  AND NOT (c)-[:PURCHASED]->(related)
RETURN related.model AS 推荐产品,
       related.category AS 产品类别,
       related.list_price AS 价格
ORDER BY related.list_price DESC
```

---

## 三、Agent 通信与协作协议

### 3.1 通信协议规范

```protobuf
syntax = "proto3";
package agent;

message AgentMessage {
    string message_id = 1;
    string correlation_id = 2;
    string from_agent = 3;
    string to_agent = 4;
    MessageType message_type = 5;
    int64 timestamp = 6;

    oneof payload {
        TaskRequest task_request = 10;
        TaskResponse task_response = 11;
        TaskNotification task_notification = 12;
        Heartbeat heartbeat = 13;
    }

    map<string, string> metadata = 20;
}

enum MessageType {
    TASK_REQUEST = 0;
    TASK_RESPONSE = 1;
    TASK_NOTIFICATION = 2;
    HEARTBEAT = 3;
    BROADCAST = 5;
}

message TaskRequest {
    string task_id = 1;
    string task_type = 2;
    string action = 3;
    map<string, Value> input_params = 4;
    Context context = 5;
    ExecutionPolicy execution_policy = 6;
    repeated string dependencies = 7;
    OutputSchema expected_output = 8;
}

message Context {
    string session_id = 1;
    string user_id = 2;
    string customer_id = 3;
    string opportunity_id = 4;
    string conversation_summary = 10;
    repeated MemoryReference memories = 11;
    map<string, TaskResponse> upstream_results = 12;
}

message ExecutionPolicy {
    int32 timeout_ms = 1;
    int32 max_retries = 2;
    RetryStrategy retry_strategy = 3;
    bool allow_fallback = 4;
    string fallback_agent = 5;
}

enum RetryStrategy {
    IMMEDIATE = 0;
    EXPONENTIAL_BACKOFF = 1;
    CIRCUIT_BREAKER = 2;
}

message TaskResponse {
    string task_id = 1;
    TaskStatus status = 2;
    map<string, Value> output_data = 3;
    TextResult text_result = 10;
    StructuredResult structured_result = 11;
    ErrorResult error_result = 12;
    ResponseMeta meta = 20;
}

enum TaskStatus {
    SUCCESS = 0;
    PARTIAL_SUCCESS = 1;
    FAILURE = 2;
    TIMEOUT = 3;
    CANCELLED = 4;
}

message ResponseMeta {
    int64 processing_time_ms = 1;
    float confidence = 2;
    repeated string source_knowledge = 3;
    repeated string uncertainty = 4;
    repeated string suggestions = 5;
}

message Value {
    oneof value {
        string string_value = 1;
        int64 int_value = 2;
        double double_value = 3;
        bool bool_value = 4;
    }
}
```

### 3.2 协作模式实现

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| **串行协作** | Agent A输出作为Agent B输入 | 产品检索->话术生成 |
| **并行协作** | 多个Agent同时执行，结果聚合 | 客户画像+产品推荐+话术生成 |
| **监督协作** | 一个Agent执行，另一个Agent审核 | 话术生成+质检审核 |
| **竞争协作** | 多个Agent生成不同方案，择优 | 多版本话术生成 |
| **循环协作** | 多轮迭代优化 | 复杂方案制定 |

```python
# 并行协作示例
async def parallel_collaboration(master, tasks, context):
    futures = []
    for task in tasks:
        agent = master.router.route(task)
        future = asyncio.create_task(agent.execute(task, context))
        futures.append(future)

    results = await asyncio.gather(*futures, return_exceptions=True)
    return results

# 监督协作示例
async def supervisory_collaboration(master, primary_task, supervisory_task, context):
    primary_agent = master.router.route(primary_task)
    primary_result = await primary_agent.execute(primary_task, context)

    supervisory_task.input_params["content_to_review"] = primary_result.output_data
    supervisory_agent = master.router.route(supervisory_task)
    review_result = await supervisory_agent.execute(supervisory_task, context)

    if review_result.output_data.get("passed", False):
        return primary_result
    else:
        return await self._correct_output(primary_result, review_result)
```

---

## 四、API 接口设计

### 4.1 接口总览

| 模块 | 接口路径 | 方法 | 说明 |
|------|----------|------|------|
| 对话 | /conversations/{id}/messages | POST | 发送消息 |
| 对话 | /conversations/{id}/messages/stream | POST | 流式消息 |
| 对话 | /conversations | GET | 获取会话列表 |
| 对话 | /conversations/{id} | GET | 获取会话详情 |
| Agent | /agents | GET | 获取Agent列表 |
| Agent | /agents/{id} | GET | 获取Agent详情 |
| Agent | /agents/{id}/execute | POST | 直接调用Agent |
| 知识库 | /knowledge/search | POST | 知识搜索 |
| 知识库 | /knowledge/graph/query | POST | 图谱查询 |
| 知识库 | /knowledge/documents | POST | 上传文档 |
| 客户 | /customers/{id}/profile | GET | 客户画像 |
| 客户 | /customers/{id}/timeline | GET | 客户时间线 |
| 同步 | /sync/erp | POST | ERP数据同步 |
| 同步 | /sync/crm | POST | CRM数据同步 |
| 系统 | /health | GET | 健康检查 |
| 系统 | /metrics | GET | 监控指标 |

### 4.2 核心接口详解

#### 4.2.1 发送消息

```http
POST /v1/conversations/{conversation_id}/messages
Content-Type: application/json
Authorization: Bearer {token}
X-Request-ID: {uuid}

Request:
{
    "content": "客户觉得我们850Pro价格太贵了，比竞品高20%，我该怎么回？",
    "content_type": "text",
    "context": {
        "customer_id": "CUST_001",
        "opportunity_id": "OPP_001",
        "product_model": "VMC-850Pro"
    },
    "options": {
        "enable_deep_thinking": true,
        "response_format": "detailed"
    }
}

Response:
{
    "code": 0,
    "message": "success",
    "data": {
        "message_id": "msg_abc123",
        "conversation_id": "conv_xyz789",
        "content": "## 【建议话术】\n王总，非常感谢您这么坦诚地反馈...",
        "agent_trace": {
            "intent": {
                "domain": "script",
                "intent": "objection_handling",
                "confidence": 0.95
            },
            "executed_agents": [
                {"agent_type": "product_expert", "task": "get_product_info", "duration_ms": 1200},
                {"agent_type": "product_expert", "task": "get_competitor_comparison", "duration_ms": 800},
                {"agent_type": "customer_expert", "task": "get_customer_profile", "duration_ms": 600},
                {"agent_type": "script_expert", "task": "generate_objection_response", "duration_ms": 2500},
                {"agent_type": "quality_inspector", "task": "validate_response", "duration_ms": 500}
            ],
            "knowledge_sources": ["product_kb_v2.1", "erp_inventory", "customer_crm"]
        },
        "suggested_actions": [
            {
                "action_type": "send_message",
                "title": "发送建议话术给客户",
                "params": {"channel": "wechat", "content": "{{response}}"}
            },
            {
                "action_type": "create_task",
                "title": "确认竞品具体型号",
                "params": {"due_date": "2026-05-21", "priority": "high"}
            }
        ],
        "related_info": {
            "customer_card": {
                "customer_id": "CUST_001",
                "name": "广州山河科技",
                "industry": "汽车零部件",
                "customer_level": "A"
            },
            "product_cards": [
                {
                    "product_id": "PROD_001",
                    "model": "VMC-850Pro",
                    "list_price": 285000,
                    "stock_status": "in_stock",
                    "stock_qty": 5
                }
            ]
        }
    }
}
```

#### 4.2.2 流式消息接口

```http
POST /v1/conversations/{conversation_id}/messages/stream
Content-Type: application/json
Accept: text/event-stream

# SSE响应

event: agent_start
data: {"agent": "product_expert", "task": "get_product_info"}

event: agent_complete
data: {"agent": "product_expert", "duration_ms": 1200}

event: content
data: {"chunk": "王总，非常感谢您", "index": 0}

event: content
data: {"chunk": "这么坦诚地反馈", "index": 1}

event: strategy_annotation
data: {"type": "value_transfer", "description": "从'为什么贵'转向'贵得值'"}

event: complete
data: {"message_id": "msg_abc123", "total_tokens": 500}
```

#### 4.2.3 知识库搜索

```http
POST /v1/knowledge/search
Content-Type: application/json

Request:
{
    "query": "适合钛合金加工的高刚性机床",
    "search_type": "hybrid",
    "filters": {
        "category": "product",
        "source": "product_manual"
    },
    "top_k": 10
}

Response:
{
    "code": 0,
    "data": {
        "results": [
            {
                "id": "PROD_001",
                "title": "VMC-850Pro 高刚性立式加工中心",
                "content": "专为重切削设计，米汉纳铸铁床身...",
                "source": "product_manual_v2.1",
                "relevance_score": 0.96,
                "metadata": {
                    "category": "product",
                    "tags": ["高刚性", "钛合金"]
                }
            }
        ],
        "total": 15,
        "search_time_ms": 350
    }
}
```

#### 4.2.4 图谱查询

```http
POST /v1/knowledge/graph/query
Content-Type: application/json

Request:
{
    "cypher": "MATCH (p:Product {model: $model})-[:HAS_PART]->(part) RETURN part.name, part.part_type",
    "parameters": {
        "model": "VMC-850Pro"
    }
}

Response:
{
    "code": 0,
    "data": [
        {"part.name": "24把圆盘刀库", "part.part_type": "标配"},
        {"part.name": "台湾潭兴第四轴", "part.part_type": "选配"}
    ],
    "columns": ["part.name", "part.part_type"]
}
```

#### 4.2.5 客户画像

```http
GET /v1/customers/{customer_id}/profile?include=basic,contacts,orders,communications,insights

Response:
{
    "code": 0,
    "data": {
        "basic_info": {
            "customer_id": "CUST_001",
            "name": "广州山河科技",
            "industry": "汽车零部件",
            "scale": "中型",
            "region": "华南"
        },
        "contacts": [
            {
                "contact_id": "CONT_001",
                "name": "王建国",
                "title": "生产总监",
                "decision_role": "技术决策者",
                "decision_weight": 0.7
            }
        ],
        "purchase_history": [
            {
                "order_id": "SO-1001",
                "date": "2025-09-20",
                "product": "VMC-850Pro",
                "amount": 520000,
                "status": "completed"
            }
        ],
        "ai_insights": {
            "key_pain_points": ["加工效率低", "设备稳定性不足"],
            "unmet_needs": ["自动化升级", "工艺优化"],
            "repurchase_potential": "high",
            "churn_risk": "low",
            "recommended_actions": [
                {
                    "action": "推荐第四轴选配方案",
                    "priority": "high",
                    "expected_outcome": "提升加工效率30%"
                }
            ]
        }
    }
}
```

#### 4.2.6 ERP数据同步

```http
POST /v1/sync/erp
Content-Type: application/json

Request:
{
    "sync_type": "incremental",
    "data_types": ["inventory", "price", "order"],
    "webhook_url": "https://callback.example.com/sync/complete"
}

Response:
{
    "code": 0,
    "data": {
        "sync_task_id": "sync_20260520_001",
        "status": "queued",
        "estimated_duration_seconds": 180
    }
}
```

### 4.3 错误码定义

| 错误码 | 说明 | HTTP状态 |
|--------|------|----------|
| 0 | 成功 | 200 |
| 400001 | 参数错误 | 400 |
| 400002 | 无效的Agent类型 | 400 |
| 400003 | 会话不存在 | 404 |
| 400004 | 消息内容过长 | 400 |
| 401001 | 认证失败 | 401 |
| 403001 | 权限不足 | 403 |
| 429001 | 请求过于频繁 | 429 |
| 500001 | 内部服务错误 | 500 |
| 500002 | Agent执行失败 | 500 |
| 500003 | LLM服务不可用 | 503 |
| 500004 | 知识库查询失败 | 500 |

---

## 五、数据模型设计

### 5.1 核心实体关系图 (ERD)

```
┌──────────────────────────────────────────────────────────────────────┐
│                        数据模型设计                                   │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐ │
│  │   Session    │<────────│   Message    │────────>│  AgentTask   │ │
│  │──────────────│         │──────────────│         │──────────────│ │
│  │ session_id   │    1:N  │ message_id   │   1:1   │ task_id      │ │
│  │ user_id      │         │ session_id   │         │ message_id   │ │
│  │ customer_id  │         │ content      │         │ agent_id     │ │
│  │ status       │         │ role         │         │ status       │ │
│  └──────────────┘         └──────────────┘         └──────────────┘ │
│         │                                                     │      │
│         │                                                     │      │
│         ▼                                                     ▼      │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐ │
│  │   Customer   │<────────│  Opportunity │<────────│    Order     │ │
│  │──────────────│         │──────────────│         │──────────────│ │
│  │ customer_id  │    1:N  │ opp_id       │   1:N   │ order_id     │ │
│  │ name         │         │ customer_id  │         │ opp_id       │ │
│  │ industry     │         │ stage        │         │ customer_id  │ │
│  │ level        │         │ amount       │         │ total_amount │ │
│  │ tags[]       │         │ win_rate     │         │ status       │ │
│  └──────────────┘         └──────────────┘         └──────────────┘ │
│         │                                                     │      │
│         │                                                     │      │
│         ▼                                                     ▼      │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐ │
│  │   Contact    │         │   Product    │         │   Ticket     │ │
│  │──────────────│         │──────────────│         │──────────────│ │
│  │ contact_id   │         │ product_id   │         │ ticket_id    │ │
│  │ customer_id  │         │ model        │         │ customer_id  │ │
│  │ name         │         │ name         │         │ order_id     │ │
│  │ title        │         │ category     │         │ type         │ │
│  │ decision_role│         │ list_price   │         │ priority     │ │
│  └──────────────┘         └──────────────┘         └──────────────┘ │
│                                                                      │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐ │
│  │  Knowledge   │         │   Graph      │         │   Memory     │ │
│  │   Source     │         │   Entity     │         │   Entry      │ │
│  │──────────────│         │──────────────│         │──────────────│ │
│  │ source_id    │         │ entity_id    │         │ memory_id    │ │
│  │ type         │         │ type         │         │ session_id   │ │
│  │ title        │         │ name         │         │ key          │ │
│  │ content      │         │ properties{} │         │ value        │ │
│  │ status       │         │ source_id    │         │ importance   │ │
│  └──────────────┘         └──────────────┘         └──────────────┘ │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.2 核心表结构

#### 5.2.1 会话表 (sessions)

```sql
CREATE TABLE sessions (
    session_id          VARCHAR(64) PRIMARY KEY,
    user_id             VARCHAR(64) NOT NULL,
    customer_id         VARCHAR(64),
    opportunity_id      VARCHAR(64),
    title               VARCHAR(255),
    context_snapshot    JSON,
    status              VARCHAR(20) DEFAULT 'active',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    closed_at           TIMESTAMP,
    metadata            JSON,

    INDEX idx_user_id (user_id),
    INDEX idx_customer_id (customer_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 5.2.2 消息表 (messages)

```sql
CREATE TABLE messages (
    message_id          VARCHAR(64) PRIMARY KEY,
    session_id          VARCHAR(64) NOT NULL,
    parent_message_id   VARCHAR(64),
    role                VARCHAR(20) NOT NULL,
    agent_id            VARCHAR(64),
    content_type        VARCHAR(20) DEFAULT 'text',
    content             TEXT,
    content_structured  JSON,
    attachments         JSON,
    token_count         INT,
    processing_time_ms  INT,
    status              VARCHAR(20) DEFAULT 'completed',
    error_info          JSON,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_session_id (session_id),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 5.2.3 Agent任务表 (agent_tasks)

```sql
CREATE TABLE agent_tasks (
    task_id             VARCHAR(64) PRIMARY KEY,
    message_id          VARCHAR(64) NOT NULL,
    agent_id            VARCHAR(64) NOT NULL,
    parent_task_id      VARCHAR(64),
    task_type           VARCHAR(50) NOT NULL,
    input_data          JSON,
    output_data         JSON,
    status              VARCHAR(20) DEFAULT 'pending',
    confidence          DECIMAL(5,4),
    started_at          TIMESTAMP,
    completed_at        TIMESTAMP,
    processing_time_ms  INT,
    retry_count         INT DEFAULT 0,
    error_info          JSON,

    INDEX idx_message_id (message_id),
    INDEX idx_agent_id (agent_id),
    INDEX idx_status (status),
    FOREIGN KEY (message_id) REFERENCES messages(message_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 5.2.4 客户画像表 (customer_profiles)

```sql
CREATE TABLE customer_profiles (
    customer_id         VARCHAR(64) PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,
    industry            VARCHAR(100),
    sub_industry        VARCHAR(100),
    scale               VARCHAR(50),
    region              VARCHAR(100),
    customer_level      VARCHAR(10) DEFAULT 'C',
    total_revenue       DECIMAL(18,2),
    total_orders        INT DEFAULT 0,
    first_order_date    DATE,
    last_order_date     DATE,
    tags                JSON,
    custom_fields       JSON,
    ai_profile          JSON,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_industry (industry),
    INDEX idx_region (region),
    INDEX idx_level (customer_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 5.2.5 联系人表 (contacts)

```sql
CREATE TABLE contacts (
    contact_id          VARCHAR(64) PRIMARY KEY,
    customer_id         VARCHAR(64) NOT NULL,
    name                VARCHAR(100) NOT NULL,
    title               VARCHAR(100),
    department          VARCHAR(100),
    decision_role       VARCHAR(50),
    decision_weight     DECIMAL(3,2),
    phone               VARCHAR(50),
    email               VARCHAR(255),
    wechat_id           VARCHAR(100),
    personality         JSON,
    relationship_level  INT DEFAULT 0,
    last_contact_date   DATE,
    notes               TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_customer_id (customer_id),
    INDEX idx_decision_role (decision_role),
    FOREIGN KEY (customer_id) REFERENCES customer_profiles(customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 5.2.6 产品主数据表 (products)

```sql
CREATE TABLE products (
    product_id          VARCHAR(64) PRIMARY KEY,
    model               VARCHAR(100) NOT NULL,
    name                VARCHAR(255) NOT NULL,
    category            VARCHAR(100) NOT NULL,
    sub_category        VARCHAR(100),
    brand               VARCHAR(100),
    description         TEXT,
    specifications      JSON,
    list_price          DECIMAL(18,2),
    cost_price          DECIMAL(18,2),
    currency            VARCHAR(10) DEFAULT 'CNY',
    stock_qty           INT DEFAULT 0,
    stock_status        VARCHAR(20) DEFAULT 'out_of_stock',
    lead_time_days      INT,
    warranty_months     INT,
    status              VARCHAR(20) DEFAULT 'active',
    images              JSON,
    documents           JSON,
    ai_summary          TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_model (model),
    INDEX idx_category (category),
    INDEX idx_status (status),
    INDEX idx_stock_status (stock_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 5.2.7 知识源表 (knowledge_sources)

```sql
CREATE TABLE knowledge_sources (
    source_id           VARCHAR(64) PRIMARY KEY,
    source_type         VARCHAR(50) NOT NULL,
    title               VARCHAR(500) NOT NULL,
    content             LONGTEXT,
    content_raw         LONGBLOB,
    file_type           VARCHAR(50),
    file_size           BIGINT,
    url                 VARCHAR(1000),
    metadata            JSON,
    extraction_status   VARCHAR(20) DEFAULT 'pending',
    extraction_result   JSON,
    entity_count        INT DEFAULT 0,
    relation_count      INT DEFAULT 0,
    status              VARCHAR(20) DEFAULT 'active',
    created_by          VARCHAR(64),
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_source_type (source_type),
    INDEX idx_extraction_status (extraction_status),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 5.2.8 记忆表 (memory_entries)

```sql
CREATE TABLE memory_entries (
    memory_id           VARCHAR(64) PRIMARY KEY,
    session_id          VARCHAR(64),
    user_id             VARCHAR(64),
    customer_id         VARCHAR(64),
    memory_type         VARCHAR(50) NOT NULL,
    memory_key          VARCHAR(255) NOT NULL,
    memory_value        TEXT NOT NULL,
    importance          INT DEFAULT 5,
    confidence          DECIMAL(5,4) DEFAULT 1.0,
    source              VARCHAR(100),
    expiration_date     DATE,
    access_count        INT DEFAULT 0,
    last_accessed_at    TIMESTAMP,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_session_id (session_id),
    INDEX idx_user_id (user_id),
    INDEX idx_customer_id (customer_id),
    INDEX idx_memory_type (memory_type),
    INDEX idx_importance (importance)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 六、部署架构设计

### 6.1 系统部署架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              部署架构                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        负载均衡层 (Nginx/ALB)                        │    │
│  │                    SSL终止 + 限流 + 路由分发                         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                      │
│         ┌────────────────────────────┼────────────────────────────┐         │
│         ▼                            ▼                            ▼         │
│  ┌──────────────┐            ┌──────────────┐            ┌──────────────┐   │
│  │   API网关     │            │   WebSocket   │            │   管理后台    │   │
│  │   (REST)      │            │   网关        │            │   (Admin)     │   │
│  └──────────────┘            └──────────────┘            └──────────────┘   │
│         │                            │                            │         │
│         └────────────────────────────┼────────────────────────────┘         │
│                                      ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     应用服务层 (Kubernetes)                          │    │
│  │                                                                      │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐   │    │
│  │  │ Master     │  │ Agent      │  │ Agent      │  │ Agent      │   │    │
│  │  │ Agent      │  │ Service 1  │  │ Service 2  │  │ Service N  │   │    │
│  │  │ (调度器)    │  │ (产品专家)  │  │ (客户专家)  │  │ (...)      │   │    │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘   │    │
│  │                                                                      │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐   │    │
│  │  │ Intent     │  │ Task       │  │ Response   │  │ Memory     │   │    │
│  │  │ Classifier │  │ Decomposer │  │ Synthesizer│  │ Manager    │   │    │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘   │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                      │
│         ┌────────────────────────────┼────────────────────────────┐         │
│         ▼                            ▼                            ▼         │
│  ┌──────────────┐            ┌──────────────┐            ┌──────────────┐   │
│  │   向量数据库   │            │   图数据库    │            │   关系数据库  │   │
│  │  (Milvus)    │            │  (Neo4j)     │            │  (MySQL)     │   │
│  │  语义检索     │            │  知识图谱     │            │  业务数据     │   │
│  └──────────────┘            └──────────────┘            └──────────────┘   │
│         │                            │                            │         │
│         └────────────────────────────┼────────────────────────────┘         │
│                                      ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        数据层                                        │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │    │
│  │  │ Redis    │  │ Kafka    │  │ MinIO    │  │ ES       │          │    │
│  │  │ 缓存     │  │ 消息队列  │  │ 对象存储  │  │ 搜索引擎  │          │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     外部系统集成层                                    │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │    │
│  │  │ ERP      │  │ CRM      │  │ LLM API  │  │ 外部数据  │          │    │
│  │  │ 系统     │  │ 系统     │  │ (GPT/Claude)│  │ 源       │          │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 服务拆分与资源需求

| 服务 | 职责 | 实例数 | CPU | 内存 | 存储 |
|------|------|--------|-----|------|------|
| api-gateway | API网关、认证、限流 | 2 | 2核 | 4G | 20G |
| master-agent | Master Agent调度 | 3 | 4核 | 8G | 50G |
| agent-product | 产品专家Agent | 2 | 4核 | 8G | 50G |
| agent-customer | 客户专家Agent | 2 | 4核 | 8G | 50G |
| agent-lead | 线索专家Agent | 2 | 4核 | 8G | 50G |
| agent-opportunity | 商机专家Agent | 2 | 4核 | 8G | 50G |
| agent-script | 话术专家Agent | 2 | 4核 | 8G | 50G |
| agent-quality | 质检专家Agent | 2 | 4核 | 8G | 50G |
| intent-service | 意图识别服务 | 2 | 4核 | 8G | 30G |
| memory-service | 记忆管理服务 | 2 | 4核 | 8G | 100G |
| knowledge-service | 知识库服务 | 2 | 4核 | 8G | 100G |
| sync-service | 数据同步服务 | 2 | 2核 | 4G | 50G |
| notification-service | 通知服务 | 2 | 2核 | 4G | 20G |

### 6.3 数据库选型

| 数据库 | 用途 | 选型 | 理由 |
|--------|------|------|------|
| 关系数据库 | 业务数据 | MySQL 8.0 | 成熟稳定，事务支持 |
| 向量数据库 | 语义检索 | Milvus | 高性能向量检索 |
| 图数据库 | 知识图谱 | Neo4j | 原生图存储，Cypher查询 |
| 缓存 | 热点数据 | Redis Cluster | 高性能缓存 |
| 消息队列 | 异步通信 | Kafka | 高吞吐消息处理 |
| 对象存储 | 文件存储 | MinIO | 兼容S3协议 |
| 搜索引擎 | 全文检索 | Elasticsearch | 分布式搜索 |

---

## 七、安全与合规设计

### 7.1 数据安全

| 层级 | 措施 | 说明 |
|------|------|------|
| 传输安全 | 全站HTTPS，TLS 1.3 | 防止中间人攻击 |
| 存储安全 | AES-256加密，数据库TDE | 敏感数据加密存储 |
| 访问控制 | RBAC权限模型 | 基于角色的访问控制 |
| 字段级权限 | 动态脱敏 | 底价、成本价等敏感字段分级保护 |
| 审计日志 | 全量操作审计 | 保留180天，支持追溯 |
| 数据隔离 | 多租户架构 | 企业数据物理隔离 |

### 7.2 内容安全

| 措施 | 说明 |
|------|------|
| 输出审核 | 敏感信息过滤（底价、折扣等内部数据） |
| 幻觉检测 | Agent输出事实性校验，引用来源追溯 |
| 合规检查 | 话术合规性自动检查（承诺、保证等敏感词） |
| 人工复核 | 高风险场景（如报价、合同）强制人工确认 |
| 数据溯源 | 所有AI生成内容标记来源Agent和知识库版本 |

### 7.3 权限矩阵

| 角色 | 产品数据 | 客户数据 | 价格数据 | 知识库管理 | 系统配置 |
|------|----------|----------|----------|-----------|----------|
| 销售人员 | 查看 | 自己的客户 | 指导价 | 无 | 无 |
| 销售主管 | 查看 | 团队客户 | 底价 | 无 | 无 |
| 产品经理 | 管理 | 查看 | 成本价 | 管理 | 无 |
| 系统管理员 | 管理 | 管理 | 管理 | 管理 | 管理 |

---

## 八、监控与运维

### 8.1 监控指标

| 类别 | 指标 | 告警阈值 | 采集频率 |
|------|------|----------|----------|
| 性能 | API响应时间P99 | > 5s | 实时 |
| 性能 | Agent执行时间 | > 10s | 实时 |
| 可用性 | 服务可用率 | < 99.9% | 1分钟 |
| 业务 | 意图识别准确率 | < 85% | 每小时 |
| 业务 | Agent任务失败率 | > 5% | 实时 |
| 资源 | CPU使用率 | > 80% | 1分钟 |
| 资源 | 内存使用率 | > 85% | 1分钟 |
| 资源 | 磁盘使用率 | > 80% | 5分钟 |

### 8.2 日志规范

```json
{
  "timestamp": "2026-05-20T15:39:00.123Z",
  "level": "INFO",
  "service": "master-agent",
  "trace_id": "trace_abc123",
  "span_id": "span_def456",
  "user_id": "user_xxx",
  "session_id": "session_yyy",
  "event_type": "agent_dispatch",
  "event_data": {
    "intent": "price_objection",
    "agents": ["product_expert", "script_expert"],
    "processing_time_ms": 3200
  },
  "message": "Successfully dispatched to 2 agents"
}
```

---

## 九、实施路线图

### 9.1 阶段规划

| 阶段 | 时间 | 目标 | 交付内容 |
|------|------|------|----------|
| **Phase 1** | M1-M2 | 基础能力建设 | Master Agent + 产品专家Agent + 话术专家Agent + 知识工厂V1 |
| **Phase 2** | M3-M4 | 核心场景覆盖 | 客户专家Agent + ERP集成 + CRM集成 + 质检专家Agent |
| **Phase 3** | M5-M6 | 全流程赋能 | 线索专家Agent + 商机专家Agent + 多Agent协同优化 |
| **Phase 4** | M7-M8 | 智能化升级 | 自学习机制 + 预测分析 + 自动化工作流 |
| **Phase 5** | M9-M12 | 生态扩展 | 开放Agent市场 + 行业解决方案 + 合作伙伴集成 |

### 9.2 MVP功能清单

**MVP必须包含**：
1. Master Agent基础调度能力（意图识别 + Agent路由）
2. 产品专家Agent（检索 + 对比 + 库存查询 + 价格查询）
3. 话术专家Agent（异议处理 + 话术生成 + 邮件生成）
4. 极简聊天界面（Web + 移动端）
5. 知识库基础接入（产品文档 + 培训资料 + 案例库）
6. ERP库存/价格查询集成
7. 客户基础画像（CRM数据同步）

---

## 十、附录

### 10.1 术语表

| 术语 | 英文 | 说明 |
|------|------|------|
| Agent | Agent | 具备特定专业能力的AI智能体 |
| Master Agent | Master Agent | 主控Agent，负责调度和协调 |
| Skill | Skill | Agent的能力单元，可独立调用 |
| RAG | Retrieval-Augmented Generation | 检索增强生成 |
| KG | Knowledge Graph | 知识图谱 |
| MCP | Model Context Protocol | 模型上下文协议 |
| DAG | Directed Acyclic Graph | 有向无环图（任务依赖） |

### 10.2 参考文档

- 磐石AI销售大脑产品介绍
- 企业现有ERP/CRM系统接口文档
- 销售方法论培训资料（SPIN、MEDDIC）
- Neo4j Cypher查询语言参考
- OpenAPI 3.0规范

---

> **文档结束**
>
> 本文档为数字分身Agent系统的详细设计文档，涵盖Master Agent调度算法、知识图谱Schema、API接口、数据模型、部署架构等核心模块。
> 后续需根据实际业务场景和技术选型进行细化调整。

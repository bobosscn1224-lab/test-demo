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


---

## 十一、Agent Skill 详细定义

### 11.1 Skill 设计规范

每个Agent由多个Skill组成，Skill是可独立调用的最小能力单元。

```yaml
skill_spec:
  skill_id: "product.search_by_params"
  name: "按参数搜索产品"
  description: "根据技术参数要求搜索匹配的产品"
  agent_type: "product_expert"

  input_schema:
    type: object
    required: [query]
    properties:
      query:
        type: string
        description: "搜索查询，支持自然语言"
      filters:
        type: object
        properties:
          category:
            type: string
          price_range:
            type: object
            properties:
              min: {type: number}
              max: {type: number}
      top_k:
        type: integer
        default: 10

  output_schema:
    type: object
    properties:
      products:
        type: array
        items:
          type: object
          properties:
            product_id: {type: string}
            model: {type: string}
            name: {type: string}
            match_score: {type: number}
            matched_params: {type: array}
            reason: {type: string}
      total_count: {type: integer}
      search_time_ms: {type: integer}

  execution:
    timeout_ms: 3000
    max_retries: 2
    fallback_skill: "product.basic_search"

  knowledge_dependencies:
    - "product_kb_v2.1"
    - "parameter_index"

  tools:
    - "vector_search"
    - "knowledge_graph_query"
    - "structured_filter"
```

### 11.2 产品专家Agent - Skill清单

| Skill ID | Skill名称 | 输入 | 输出 | 依赖知识库 | 典型耗时 |
|----------|----------|------|------|-----------|----------|
| product.search | 产品搜索 | 自然语言查询 | 产品列表+匹配度 | 产品知识库 | 500ms |
| product.get_detail | 获取产品详情 | product_id/model | 完整产品信息 | 产品知识库 | 200ms |
| product.compare | 产品对比 | [product_ids] | 对比表格+差异分析 | 产品知识库 | 800ms |
| product.get_params | 获取技术参数 | product_id | 参数列表+解释 | 产品知识库 | 300ms |
| product.check_inventory | 查询库存 | product_id | 库存数量+仓库+交期 | ERP库存 | 300ms |
| product.get_price | 获取价格 | product_id | 指导价+底价+促销价 | ERP价格 | 300ms |
| product.recommend_config | 推荐配置 | 应用场景+预算 | 推荐配置+选配建议 | 产品知识库+案例库 | 1500ms |
| product.cross_sell | 搭售推荐 | product_id | 关联产品列表 | 知识图谱 | 600ms |
| product.get_competitor | 获取竞品信息 | product_id | 竞品对比+应对策略 | 竞品知识库 | 500ms |
| product.get_cases | 获取相关案例 | product_id+scenario | 案例列表+话术要点 | 案例库 | 700ms |
| product.calculate_roi | 计算投资回报 | product_id+客户信息 | ROI分析+回本周期 | 案例库+计算器 | 1000ms |

### 11.3 客户专家Agent - Skill清单

| Skill ID | Skill名称 | 输入 | 输出 | 依赖知识库 | 典型耗时 |
|----------|----------|------|------|-----------|----------|
| customer.get_profile | 获取客户画像 | customer_id | 360度画像 | CRM+订单+沟通记录 | 800ms |
| customer.research | 客户背调 | company_name | 企业信息+决策人+动态 | 互联网+工商数据 | 2000ms |
| customer.analyze_contacts | 分析决策链 | customer_id | 决策地图+关系强度 | CRM联系人 | 600ms |
| customer.get_timeline | 获取时间线 | customer_id+date_range | 互动时间线 | 沟通记录 | 500ms |
| customer.follow_up_strategy | 跟进策略 | customer_id+current_status | 跟进建议+话术 | 客户画像+历史 | 1200ms |
| customer.complaint_analysis | 客诉分析 | ticket_id | 根因分析+处理建议 | 工单系统 | 1000ms |
| customer.predict_churn | 流失预测 | customer_id | 风险等级+预警信号 | 历史数据 | 800ms |
| customer.segment_analysis | 客户分群 | customer_id | 客户分群+特征标签 | 客户数据 | 700ms |

### 11.4 话术专家Agent - Skill清单

| Skill ID | Skill名称 | 输入 | 输出 | 依赖知识库 | 典型耗时 |
|----------|----------|------|------|-----------|----------|
| script.handle_objection | 异议处理 | objection_type+context | 回复话术+策略注解 | 话术库+产品知识 | 1500ms |
| script.generate_email | 生成邮件 | email_type+context | 完整邮件+主题行 | 邮件模板库 | 1000ms |
| script.polish | 话术润色 | raw_text+target_style | 优化后话术 | 话术库 | 800ms |
| script.negotiation_assist | 谈判辅助 | negotiation_stage+context | 谈判策略+话术要点 | 谈判案例库 | 1200ms |
| script.translate | 多语言翻译 | text+target_language | 翻译后文本 | 术语词典 | 600ms |
| script.generate_proposal | 生成方案书 | opportunity_id | 方案书大纲+内容 | 模板库+产品知识 | 2000ms |
| script.role_play | 角色扮演 | scenario+role | 模拟对话+应对建议 | 场景库 | 1500ms |

### 11.5 商机专家Agent - Skill清单

| Skill ID | Skill名称 | 输入 | 输出 | 依赖知识库 | 典型耗时 |
|----------|----------|------|------|-----------|----------|
| opportunity.assess | 商机评估 | opportunity_id | 赢率+预计金额+成交时间 | 历史商机数据 | 1000ms |
| opportunity.analyze_stage | 阶段分析 | opportunity_id | 阶段诊断+推进障碍 | 商机数据 | 800ms |
| opportunity.generate_strategy | 生成推进策略 | opportunity_id | 下一步行动+关键里程碑 | 销售方法论 | 1500ms |
| opportunity.risk_analysis | 风险分析 | opportunity_id | 风险清单+应对措施 | 历史丢单案例 | 1000ms |
| opportunity.competitive_intel | 竞争情报 | opportunity_id | 竞品参与情况+差异化策略 | 竞品库 | 1200ms |
| opportunity.quotation_strategy | 报价策略 | opportunity_id+budget | 报价方案+谈判策略 | 价格策略库 | 1200ms |
| opportunity.contract_review | 合同审核 | contract_text | 风险点+修改建议 | 合同模板库 | 1000ms |

### 11.6 质检专家Agent - Skill清单

| Skill ID | Skill名称 | 输入 | 输出 | 依赖知识库 | 典型耗时 |
|----------|----------|------|------|-----------|----------|
| quality.fact_check | 事实核查 | text | 事实错误+纠正建议 | 产品知识库+ERP | 800ms |
| quality.compliance_check | 合规检查 | text | 合规风险+修改建议 | 合规规则库 | 600ms |
| quality.skill_assessment | 技巧评估 | conversation_record | 技巧评分+改进建议 | 销售培训资料 | 1000ms |
| quality.omission_detect | 遗漏识别 | text+context | 遗漏项+补充建议 | 标准流程库 | 700ms |
| quality.visit_audit | 拜访审计 | visit_record | 审计报告+改进方案 | 拜访标准 | 1200ms |
| quality.response_validate | 响应验证 | agent_response | 验证结果+修改建议 | 质量标准 | 500ms |

---

## 十二、前端交互原型设计

### 12.1 极简聊天界面

```
+-------------------------------------------------------------+
|  [图标] 数字分身 - 销售大脑              [用户] [设置]       |
+-------------------------------------------------------------+
|                                                             |
|  +---------------------------------------------------------+|
|  | [机器人] 我是您的AI销售军师，随时为您提供支持。           ||
|  |          无论是查产品、写话术、还是分析客户，我都能帮您。  ||
|  |          请随时告诉我您当前遇到的最紧迫问题或场景。       ||
|  +---------------------------------------------------------+|
|                                                             |
|  快捷入口：                                                 |
|  +--------+ +--------+ +--------+ +--------+ +--------+    |
|  |客户背调| |实时辅助| |导入聊天| |拜访质检| |生成话术|    |
|  +--------+ +--------+ +--------+ +--------+ +--------+    |
|                                                             |
|  +---------------------------------------------------------+|
|  | [历史对话区域]                                            ||
|  |                                                         ||
|  | [用户] 客户觉得我们850Pro价格太贵了，比竞品高20%         ||
|  |                                                         ||
|  | [机器人]                                                 ||
|  | +-----------------------------------------------------+ ||
|  | | 【建议话术】                                         | ||
|  | | 王总，非常感谢您这么坦诚地反馈...                    | ||
|  | |                                                     | ||
|  | | 【策略注解】                                         | ||
|  | | - 价值重构与转移：从"为什么贵"转向"贵得值"          | ||
|  | | - 硬件锚定与现货优势：详细拆解高价值配置              | ||
|  | | - 从防御到进攻：主动邀请客户进行成本分析              | ||
|  | |                                                     | ||
|  | | 【数据支撑】                                         | ||
|  | | - 扭矩输出比日系竞品高15% [产品手册v2.1]              | ||
|  | | - 现货5台，7天交货 [ERP实时库存]                      | ||
|  | |                                                     | ||
|  | | 【待确认信息】                                       | ||
|  | | [ ] 客户所指的"竞品"具体品牌和型号？                  | ||
|  | | [ ] 客户主要用它加工什么材料？                        | ||
|  | |                                                     | ||
|  | | 【下一步行动】                                       | ||
|  | | 1. 发送建议话术给客户                                 | ||
|  | | 2. 确认竞品具体型号，准备详细对比资料                  | ||
|  | | 3. 邀请客户参观展厅或现场测试                         | ||
|  | +-----------------------------------------------------+ ||
|  |                                                         ||
|  | [客户卡片] 广州山河科技 | 汽车零部件 | A类 | 累计520万   ||
|  | [产品卡片] VMC-850Pro | 285000元 | 现货5台 | 7天交货    ||
|  |                                                         ||
|  +---------------------------------------------------------+|
|                                                             |
|  +---------------------------------------------------------+|
|  | 在此输入客户的问题、沟通摘要、询问策略...        [附件][发送]||
|  +---------------------------------------------------------+|
|                                                             |
|  [启用深度思考]  [客户档案]  [业务数据(ERP)]                 |
|                                                             |
+-------------------------------------------------------------+
```

### 12.2 客户档案侧边栏

```
+-------------------------------------------------------------+
|  客户档案 - 广州山河科技                        [编辑]       |
+-------------------------------------------------------------+
|                                                             |
|  +---------------------------------------------------------+|
|  |  [企业图标] 企业信息                                      ||
|  |  行业：汽车零部件                                        ||
|  |  规模：中型（200-500人）                                 ||
|  |  区域：华南 / 广东 / 广州                                ||
|  |  标签：[特斯拉供应商] [高精度需求] [长期合作]            ||
|  +---------------------------------------------------------+|
|                                                             |
|  +---------------------------------------------------------+|
|  |  [用户图标] 决策人地图                                    ||
|  |  [王建国] 生产总监 - 技术决策者 - 权重70%                 ||
|  |  [李梅]   采购经理 - 影响者 - 权重30%                     ||
|  |  [添加联系人]                                            ||
|  +---------------------------------------------------------+|
|                                                             |
|  +---------------------------------------------------------+|
|  |  [图表图标] 采购历史                                      ||
|  |  日期        产品      金额    状态                      ||
|  |  2025-09-20  850Pro   52万    完成                      ||
|  |  2025-06-15  650Pro   38万    完成                      ||
|  |  累计采购：520万 | 订单数：5 | 客单价：104万            ||
|  +---------------------------------------------------------+|
|                                                             |
|  +---------------------------------------------------------+|
|  |  [灯泡图标] AI洞察                                        ||
|  |  痛点：加工效率低、设备稳定性不足                        ||
|  |  需求：自动化升级、工艺优化                              ||
|  |  潜力：高（预计6个月内复购）                            ||
|  |  风险：低                                                ||
|  |  推荐行动：推荐第四轴选配方案（提升效率30%）              ||
|  +---------------------------------------------------------+|
|                                                             |
|  +---------------------------------------------------------+|
|  |  [日历图标] 跟进计划                                      ||
|  |  [ ] 5/21 发送报价方案                                   ||
|  |  [ ] 5/25 展厅参观                                       ||
|  |  [ ] 5/30 技术交流会议                                   ||
|  +---------------------------------------------------------+|
|                                                             |
+-------------------------------------------------------------+
```

### 12.3 Agent执行链路可视化

```
+-------------------------------------------------------------+
|  Agent执行链路 - 消息ID: msg_abc123      总耗时: 3.2s       |
+-------------------------------------------------------------+
|                                                             |
|  意图识别        [OK] 0.3s    script/objection_handling    |
|      |                                                      |
|      v                                                      |
|  +-------------------------------------------------------+  |
|  | 并行执行层 (1.5s)                                      |  |
|  |                                                       |  |
|  |  [产品专家] get_product_info        [OK] 0.8s         |  |
|  |  [产品专家] get_competitor_comparison [OK] 0.6s       |  |
|  |  [客户专家] get_customer_profile    [OK] 0.5s         |  |
|  |                                                       |  |
|  +-------------------------------------------------------+  |
|      |                                                      |
|      v                                                      |
|  话术生成        [OK] 1.2s    generate_objection_response   |
|      |                                                      |
|      v                                                      |
|  质量验证        [OK] 0.5s    validate_response (通过)     |
|      |                                                      |
|      v                                                      |
|  响应合成        [OK] 0.2s    最终输出                      |
|                                                             |
|  [查看详细日志]  [查看知识引用]  [重新生成]                   |
|                                                             |
+-------------------------------------------------------------+
```

---

## 十三、测试用例设计

### 13.1 测试策略总览

| 测试类型 | 覆盖范围 | 自动化程度 | 执行频率 |
|----------|----------|-----------|----------|
| 单元测试 | Skill级别 | 100% | 每次提交 |
| 集成测试 | Agent间协作 | 90% | 每次提交 |
| 端到端测试 | 完整对话流程 | 80% | 每日构建 |
| 性能测试 | 响应时间/并发 | 100% | 每周 |
| 安全测试 | 权限/注入/泄露 | 100% | 每次发布 |
| 回归测试 | 核心场景 | 100% | 每次发布 |

### 13.2 核心场景测试用例

#### TC-001: 价格异议处理（端到端）

| 步骤 | 操作 | 预期结果 | 验证点 |
|------|------|----------|--------|
| 1 | 用户输入：客户觉得850Pro太贵了，比M牌高20% | 系统识别意图为objection_handling | 意图准确率大于0.9 |
| 2 | 系统调度Agent | 并行调度产品专家+客户专家 | Agent数量等于2 |
| 3 | 产品专家执行 | 返回850Pro参数+M牌对比数据 | 数据来源为ERP+竞品库 |
| 4 | 客户专家执行 | 返回客户画像（如有） | 数据来自CRM |
| 5 | 话术专家生成回复 | 输出包含策略注解+待确认信息 | 包含value_transfer策略 |
| 6 | 质检专家验证 | 验证通过，置信度大于0.85 | 无事实错误 |
| 7 | 最终输出 | 包含建议话术+策略注解+待确认信息 | 格式符合规范 |
| 8 | 响应时间 | 总耗时小于5s | 性能达标 |

#### TC-002: 客户背调（端到端）

| 步骤 | 操作 | 预期结果 | 验证点 |
|------|------|----------|--------|
| 1 | 用户输入：帮我查一下Tesla的背景 | 识别为background_research | 意图准确率大于0.9 |
| 2 | 系统调度Agent | 并行调度网络搜索+决策人分析+购买历史 | Agent数量等于3 |
| 3 | 网络搜索执行 | 返回企业基本信息+近期动态 | 数据来源为互联网 |
| 4 | 决策人分析执行 | 返回LinkedIn关键人信息 | 数据来源为LinkedIn |
| 5 | 报告生成 | 输出结构化背调报告 | 包含5个维度 |
| 6 | 数据安全 | 不泄露内部底价信息 | 敏感字段已过滤 |

#### TC-003: 配件反查（图谱查询）

| 步骤 | 操作 | 预期结果 | 验证点 |
|------|------|----------|--------|
| 1 | 用户输入：YH-456冷却液配哪款机床？ | 识别为product_search+配件查询 | 意图准确率大于0.9 |
| 2 | 图谱查询 | 执行Cypher查询COMPATIBLE_WITH关系 | 查询耗时小于500ms |
| 3 | 返回结果 | 推荐VMC-850Pro+标配配件列表 | 推荐准确性100% |
| 4 | 库存查询 | 显示850Pro库存等于5台 | 数据来自ERP实时 |

#### TC-004: 流式响应（性能）

| 步骤 | 操作 | 预期结果 | 验证点 |
|------|------|----------|--------|
| 1 | 发送流式请求 | 建立SSE连接 | HTTP 200 |
| 2 | 接收agent_start事件 | 收到第一个Agent开始事件 | 时间小于500ms |
| 3 | 接收content事件 | 收到文本片段 | 每片段小于100ms |
| 4 | 接收complete事件 | 收到完成事件 | 总时间小于5s |
| 5 | 验证事件顺序 | agent_start到content到complete | 顺序正确 |

#### TC-005: 权限控制（安全）

| 步骤 | 操作 | 预期结果 | 验证点 |
|------|------|----------|--------|
| 1 | 普通销售查询底价 | 返回权限不足或显示指导价 | 403或脱敏 |
| 2 | 销售主管查询底价 | 返回底价数据 | 200 |
| 3 | 销售A查看销售B的客户 | 返回权限不足 | 403 |
| 4 | 跨企业数据访问 | 返回数据不存在 | 数据隔离 |

### 13.3 压力测试场景

| 场景 | 并发数 | 持续时间 | 预期指标 |
|------|--------|----------|----------|
| 日常峰值 | 100用户 | 30分钟 | P99小于3s, 错误率小于1% |
| 促销高峰 | 500用户 | 1小时 | P99小于5s, 错误率小于2% |
| 极限测试 | 1000用户 | 10分钟 | 系统不崩溃, 可降级 |
| 突发流量 | 瞬间1000到5000 | 5分钟 | 熔断生效, 限流正常 |

---

## 十四、性能优化策略

### 14.1 缓存策略

| 缓存层级 | 缓存内容 | 过期策略 | 命中率目标 |
|----------|----------|----------|-----------|
| L1 - 本地缓存 | Agent配置、Skill元数据 | 5分钟TTL | 95% |
| L2 - Redis缓存 | 产品信息、客户画像 | 1小时TTL+主动失效 | 85% |
| L3 - 向量缓存 | 嵌入向量、检索结果 | 24小时TTL | 80% |
| L4 - 数据库缓存 | 热点查询结果 | 查询结果缓存 | 70% |

### 14.2 查询优化

```python
# 产品查询优化示例
class ProductQueryOptimizer:
    def optimize(self, query: str) -> OptimizedQuery:
        # 1. 查询意图预判
        intent = self._predict_intent(query)

        # 2. 选择最优索引
        if intent == "model_lookup":
            # 精确型号查询 - 走B+树索引
            return OptimizedQuery(index="btree_model", filter="model="+query)
        elif intent == "param_search":
            # 参数范围查询 - 走向量索引
            return OptimizedQuery(index="vector_params", embedding=self._encode(query))
        elif intent == "cross_sell":
            # 搭售查询 - 走图谱遍历
            return OptimizedQuery(index="graph_relations", traversal="COMPATIBLE_WITH")

        # 3. 混合查询（RAG + KG）
        return OptimizedQuery(
            index="hybrid",
            vector_search=self._encode(query),
            graph_filter=self._extract_entities(query)
        )
```

### 14.3 限流与降级

| 策略 | 触发条件 | 处理方式 |
|------|----------|----------|
| QPS限流 | 单用户大于10 req/s | 429 Too Many Requests |
| 并发限流 | 单Agent大于50并发 | 排队等待 |
| 熔断 | 错误率大于20%持续30s | 切换备用Agent |
| 降级 | 响应时间大于10s | 返回简化版结果 |
| 负载均衡 | CPU大于80% | 自动扩容 |

---

## 十五、运维与监控

### 15.1 监控大盘

```
+-------------------------------------------------------------+
|  数字分身Agent系统 - 实时监控大盘                            |
+-------------------------------------------------------------+
|                                                             |
|  +----------+ +----------+ +----------+ +----------+       |
|  | 在线用户 | | 今日消息 | | Agent任务| | 平均响应 |       |
|  |   128    | |  3,456   | |  8,234   | |   2.3s   |       |
|  +----------+ +----------+ +----------+ +----------+       |
|                                                             |
|  +---------------------------------------------------------+|
|  | Agent健康状态                                            ||
|  | 产品专家 [健康] | 客户专家 [健康] | 话术专家 [健康]     ||
|  | 线索专家 [健康] | 商机专家 [健康] | 质检专家 [健康]     ||
|  +---------------------------------------------------------+|
|                                                             |
|  +---------------------------------------------------------+|
|  | 意图识别准确率趋势 (24h)                                 ||
|  | ################################################  94.5% ||
|  +---------------------------------------------------------+|
|                                                             |
|  +---------------------------------------------------------+|
|  | Agent任务失败率 (Top 5)                                  ||
|  | 1. 产品专家-库存查询  0.5%                               ||
|  | 2. 客户专家-背调查询  0.8%                               ||
|  | 3. 话术专家-邮件生成  1.2%                               ||
|  | 4. 商机专家-赢率预测  1.5%                               ||
|  | 5. 质检专家-事实核查  2.1%                               ||
|  +---------------------------------------------------------+|
|                                                             |
|  +---------------------------------------------------------+|
|  | 知识库更新状态                                           ||
|  | 产品知识库 [OK] 2026-05-20 14:00                        ||
|  | 案例库     [OK] 2026-05-20 13:00                        ||
|  | 竞品库     [OK] 2026-05-20 12:00                        ||
|  | 话术库     [OK] 2026-05-20 11:00                        ||
|  +---------------------------------------------------------+|
|                                                             |
+-------------------------------------------------------------+
```

### 15.2 告警规则

| 告警级别 | 触发条件 | 通知方式 | 响应时间 |
|----------|----------|----------|----------|
| P0 - 紧急 | 服务不可用大于5分钟 | 电话+短信+钉钉 | 5分钟内 |
| P1 - 严重 | 错误率大于10%持续10分钟 | 短信+钉钉 | 15分钟内 |
| P2 - 一般 | 响应时间P99大于5s持续30分钟 | 钉钉 | 30分钟内 |
| P3 - 提示 | 磁盘使用率大于80% | 钉钉 | 2小时内 |

---

## 十六、扩展性设计

### 16.1 新Agent接入规范

```python
# 新Agent接入示例：行业专家Agent
class IndustryExpertAgent(BaseAgent):
    agent_type = "industry_expert"

    skills = [
        Skill(
            skill_id="industry.analyze_trend",
            name="行业趋势分析",
            description="分析行业发展趋势和市场机会"
        ),
        Skill(
            skill_id="industry.get_benchmark",
            name="行业标杆案例",
            description="获取同行业标杆企业的最佳实践"
        ),
        Skill(
            skill_id="industry.regulation_update",
            name="政策法规更新",
            description="跟踪行业相关政策法规变化"
        )
    ]

    knowledge_sources = [
        "industry_report_kb",
        "policy_document_kb",
        "benchmark_case_kb"
    ]

    def register(self, master: MasterAgent):
        master.agent_registry.register(
            agent_type=self.agent_type,
            skills=self.skills,
            knowledge_sources=self.knowledge_sources,
            capabilities=["industry_analysis", "trend_forecast"]
        )
```

### 16.2 插件化架构

| 插件类型 | 示例 | 接入方式 |
|----------|------|----------|
| 数据源插件 | 新ERP系统、新CRM系统 | 实现DataSource接口 |
| 知识源插件 | 新行业报告源 | 实现KnowledgeSource接口 |
| Skill插件 | 新分析算法 | 实现Skill接口 |
| 工具插件 | 新计算工具 | 实现Tool接口 |
| 通知插件 | 企业微信、飞书 | 实现NotificationChannel接口 |

---

## 十七、数据治理

### 17.1 数据质量规则

| 数据类型 | 质量规则 | 校验频率 | 处理方式 |
|----------|----------|----------|----------|
| 产品数据 | 必填字段完整率大于99% | 每日 | 自动补全或告警 |
| 价格数据 | 指导价大于成本价大于底价 | 实时 | 拒绝写入 |
| 客户数据 | 手机号格式正确 | 实时 | 清洗或标记 |
| 库存数据 | 与ERP差异小于1% | 每小时 | 自动同步修正 |
| 知识数据 | 事实准确性大于95% | 每周 | 人工审核 |

### 17.2 数据生命周期

原始数据 -> 清洗 -> 提取 -> 入库 -> 索引 -> 应用 -> 归档 -> 销毁
   |         |       |      |      |      |      |      |
   |         |       |      |      |      |      |      +-- 7年后
   |         |       |      |      |      |      +-- 3年后
   |         |       |      |      |      +-- 实时使用
   |         |       |      |      +-- 构建时
   |         |       |      +-- 入库时
   |         |       +-- 提取时
   |         +-- 清洗时
   +-- 接入时

---

## 十八、灾难恢复

### 18.1 备份策略

| 数据类型 | 备份频率 | 保留周期 | 存储位置 |
|----------|----------|----------|----------|
| 业务数据库 | 每小时增量+每日全量 | 30天 | 异地双活 |
| 知识图谱 | 每日全量 | 7天 | 异地双活 |
| 向量数据 | 每日全量 | 7天 | 异地双活 |
| 会话数据 | 实时同步 | 90天 | 同城双活 |
| 配置数据 | 变更时触发 | 永久 | Git+对象存储 |

### 18.2 故障切换

| 故障场景 | 检测时间 | 切换时间 | 影响范围 |
|----------|----------|----------|----------|
| 单Agent故障 | 5s | 10s | 该Agent任务降级 |
| Master Agent故障 | 5s | 15s | 新会话受影响 |
| 数据库故障 | 10s | 30s | 读操作切换只读副本 |
| 全链路故障 | 30s | 2min | 启用离线模式 |

---

> **补充文档结束**
>
> 本文档补充了Agent Skill详细定义、前端交互原型、测试用例、性能优化、运维监控、扩展性设计、数据治理和灾难恢复等深度内容。


---

## 十九、Cypher 查询优化详解

### 19.1 查询性能优化策略

#### 19.1.1 索引设计

```cypher
// 为高频查询字段创建索引
CREATE INDEX product_model_index FOR (p:Product) ON (p.model);
CREATE INDEX product_category_index FOR (p:Product) ON (p.category);
CREATE INDEX customer_name_index FOR (c:Customer) ON (c.name);
CREATE INDEX contact_decision_role_index FOR (ct:Contact) ON (ct.decision_role);
CREATE INDEX scenario_name_index FOR (s:Scenario) ON (s.name);

// 复合索引（用于组合查询）
CREATE INDEX product_category_status_index FOR (p:Product) ON (p.category, p.status);
CREATE INDEX customer_industry_region_index FOR (c:Customer) ON (c.industry, c.region);
```

#### 19.1.2 查询优化示例

**优化前（全表扫描）**：
```cypher
// 低效查询：未使用索引，全图扫描
MATCH (p:Product)
WHERE p.model = "VMC-850Pro"
RETURN p
```

**优化后（索引命中）**：
```cypher
// 高效查询：利用索引快速定位
MATCH (p:Product {model: "VMC-850Pro"})
RETURN p
```

**优化前（笛卡尔积风险）**：
```cypher
// 低效查询：可能导致笛卡尔积
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
MATCH (p)-[:HAS_PART]->(part:Part)
RETURN c.name, p.model, part.name
```

**优化后（减少匹配范围）**：
```cypher
// 高效查询：先过滤再扩展
MATCH (p:Product {model: "VMC-850Pro"})
MATCH (c:Customer)-[:PURCHASED]->(p)
MATCH (p)-[:HAS_PART]->(part:Part)
RETURN c.name, p.model, part.name
```

### 19.2 复杂查询优化

#### 19.2.1 多层关系遍历优化

```cypher
// 场景：查找购买过某产品且其联系人中有决策者的客户
// 优化前：多层遍历无限制
MATCH (c:Customer)-[:PURCHASED]->(p:Product {model: "VMC-850Pro"})
MATCH (c)-[:HAS_CONTACT]->(ct:Contact)
WHERE ct.decision_role = "最终决策者"
RETURN c.name, ct.name

// 优化后：使用参数化查询+限制遍历深度
MATCH (c:Customer)-[:PURCHASED]->(p:Product {model: $model})
WITH c
MATCH (c)-[:HAS_CONTACT]->(ct:Contact)
WHERE ct.decision_role = $role
  AND ct.decision_weight >= $min_weight
RETURN c.name AS customer_name, 
       ct.name AS contact_name,
       ct.decision_weight AS weight
ORDER BY ct.decision_weight DESC
LIMIT $limit
```

#### 19.2.2 聚合查询优化

```cypher
// 场景：统计各行业的客户数量和总采购额
// 优化前：全图聚合
MATCH (c:Customer)-[:BELONGS_TO]->(i:Industry)
OPTIONAL MATCH (c)-[:PURCHASED]->(o:Order)
RETURN i.name, count(DISTINCT c) AS customer_count, sum(o.amount) AS total_amount

// 优化后：预聚合+使用APOC过程
CALL apoc.periodic.iterate(
  "MATCH (c:Customer)-[:BELONGS_TO]->(i:Industry) RETURN i, c",
  "MATCH (c)-[:PURCHASED]->(o:Order) 
   WITH i, c, sum(o.amount) AS customer_total 
   RETURN i.name AS industry, count(c) AS cnt, sum(customer_total) AS total",
  {batchSize: 1000, parallel: true}
)
```

### 19.3 查询计划分析

```cypher
// 查看查询执行计划
EXPLAIN
MATCH (p:Product {model: "VMC-850Pro"})-[:COMPATIBLE_WITH]->(related:Product)
RETURN related.model, related.name

// 查看查询性能统计
PROFILE
MATCH (c:Customer {name: "广州山河科技"})-[:PURCHASED]->(p:Product)
RETURN p.model, p.list_price
```

### 19.4 批量操作优化

```cypher
// 批量导入产品数据（使用apoc.periodic.iterate）
CALL apoc.periodic.iterate(
  "UNWIND $products AS product RETURN product",
  "CREATE (p:Product) 
   SET p = product
   RETURN p",
  {batchSize: 1000, iterateList: true, params: {products: $product_list}}
)

// 批量创建关系（使用apoc.periodic.iterate）
CALL apoc.periodic.iterate(
  "UNWIND $relations AS rel RETURN rel",
  "MATCH (from {id: rel.from_id}), (to {id: rel.to_id})
   CALL apoc.create.relationship(from, rel.type, rel.properties, to) YIELD rel
   RETURN rel",
  {batchSize: 500, iterateList: true, params: {relations: $relation_list}}
)
```

---

## 二十、前端组件代码实现

### 20.1 React组件架构

```typescript
// 核心组件结构
src/
├── components/
│   ├── Chat/
│   │   ├── ChatContainer.tsx      // 聊天容器
│   │   ├── MessageList.tsx        // 消息列表
│   │   ├── MessageItem.tsx        // 单条消息
│   │   ├── InputArea.tsx          // 输入区域
│   │   └── QuickActions.tsx       // 快捷入口
│   ├── Cards/
│   │   ├── CustomerCard.tsx       // 客户卡片
│   │   ├── ProductCard.tsx        // 产品卡片
│   │   └── OpportunityCard.tsx    // 商机卡片
│   ├── AgentTrace/
│   │   ├── AgentTracePanel.tsx    // Agent执行链路
│   │   └── AgentNode.tsx          // 单个Agent节点
│   └── Sidebar/
│       ├── CustomerProfile.tsx    // 客户档案
│       └── KnowledgePanel.tsx     // 知识面板
├── hooks/
│   ├── useChat.ts                  // 聊天逻辑Hook
│   ├── useAgentTrace.ts           // Agent追踪Hook
│   └── useStreaming.ts            // 流式响应Hook
├── services/
│   ├── api.ts                     // API封装
│   └── websocket.ts               // WebSocket封装
└── types/
    ├── message.ts                 // 消息类型
    ├── agent.ts                   // Agent类型
    └── knowledge.ts               // 知识类型
```

### 20.2 核心组件实现

#### 20.2.1 聊天容器组件

```typescript
// ChatContainer.tsx
import React, { useState, useCallback, useRef } from 'react';
import { MessageList } from './MessageList';
import { InputArea } from './InputArea';
import { QuickActions } from './QuickActions';
import { AgentTracePanel } from '../AgentTrace/AgentTracePanel';
import { useChat } from '../../hooks/useChat';
import { useStreaming } from '../../hooks/useStreaming';

export const ChatContainer: React.FC = () => {
  const [showTrace, setShowTrace] = useState(false);
  const [currentTrace, setCurrentTrace] = useState<AgentTrace | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    messages,
    sendMessage,
    isLoading,
    currentConversationId
  } = useChat();

  const {
    isStreaming,
    streamingContent,
    startStreaming
  } = useStreaming();

  const handleSendMessage = useCallback(async (content: string, options?: MessageOptions) => {
    // 发送消息并获取trace ID
    const response = await sendMessage(content, options);

    if (response.agent_trace) {
      setCurrentTrace(response.agent_trace);
      setShowTrace(true);
    }

    // 如果启用流式，开始接收SSE
    if (options?.enableStreaming) {
      await startStreaming(currentConversationId, response.message_id);
    }
  }, [sendMessage, currentConversationId, startStreaming]);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h2>数字分身 - 销售大脑</h2>
        <div className="header-actions">
          <button onClick={() => setShowTrace(!showTrace)}>
            {showTrace ? '隐藏链路' : '查看链路'}
          </button>
        </div>
      </div>

      <QuickActions onAction={handleSendMessage} />

      <div className="chat-main">
        <div className="chat-content">
          <MessageList 
            messages={messages}
            isStreaming={isStreaming}
            streamingContent={streamingContent}
          />
          <div ref={messagesEndRef} />
        </div>

        {showTrace && currentTrace && (
          <div className="trace-panel">
            <AgentTracePanel trace={currentTrace} />
          </div>
        )}
      </div>

      <InputArea 
        onSend={handleSendMessage}
        isLoading={isLoading || isStreaming}
      />
    </div>
  );
};
```

#### 20.2.2 消息列表组件

```typescript
// MessageList.tsx
import React from 'react';
import { MessageItem } from './MessageItem';
import { Message } from '../../types/message';

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  streamingContent: string;
}

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  isStreaming,
  streamingContent
}) => {
  return (
    <div className="message-list">
      {messages.map((message, index) => (
        <MessageItem 
          key={message.message_id}
          message={message}
          isLast={index === messages.length - 1}
        />
      ))}

      {isStreaming && (
        <div className="streaming-message">
          <div className="message-avatar">🤖</div>
          <div className="message-content">
            <div className="streaming-text">{streamingContent}</div>
            <div className="streaming-indicator">
              <span className="dot"></span>
              <span className="dot"></span>
              <span className="dot"></span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
```

#### 20.2.3 结构化消息渲染组件

```typescript
// StructuredMessage.tsx
import React from 'react';
import { CustomerCard } from '../Cards/CustomerCard';
import { ProductCard } from '../Cards/ProductCard';

interface StructuredMessageProps {
  content: string;
  structuredData: StructuredData;
}

export const StructuredMessage: React.FC<StructuredMessageProps> = ({
  content,
  structuredData
}) => {
  // 解析Markdown风格的分节内容
  const sections = parseSections(content);

  return (
    <div className="structured-message">
      {sections.map((section, index) => (
        <div key={index} className={`section section-${section.type}`}>
          <h4 className="section-title">{section.title}</h4>
          <div className="section-content">
            {section.type === 'script' && (
              <div className="script-box">
                <pre>{section.content}</pre>
                <button className="copy-btn" onClick={() => copyToClipboard(section.content)}>
                  复制话术
                </button>
              </div>
            )}

            {section.type === 'strategy' && (
              <ul className="strategy-list">
                {section.items.map((item, i) => (
                  <li key={i}>
                    <strong>{item.title}</strong>
                    <p>{item.description}</p>
                  </li>
                ))}
              </ul>
            )}

            {section.type === 'data' && (
              <div className="data-support">
                {section.items.map((item, i) => (
                  <div key={i} className="data-item">
                    <span className="data-fact">{item.fact}</span>
                    <span className="data-source">[{item.source}]</span>
                  </div>
                ))}
              </div>
            )}

            {section.type === 'todo' && (
              <div className="todo-list">
                {section.items.map((item, i) => (
                  <label key={i} className="todo-item">
                    <input type="checkbox" checked={item.checked} readOnly />
                    <span>{item.text}</span>
                  </label>
                ))}
              </div>
            )}

            {section.type === 'action' && (
              <ol className="action-list">
                {section.items.map((item, i) => (
                  <li key={i}>
                    <span className="action-step">{item.step}</span>
                    {item.deadline && (
                      <span className="action-deadline">截止: {item.deadline}</span>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      ))}

      {/* 关联信息卡片 */}
      {structuredData.related_info?.customer_card && (
        <CustomerCard data={structuredData.related_info.customer_card} />
      )}
      {structuredData.related_info?.product_cards?.map((card, i) => (
        <ProductCard key={i} data={card} />
      ))}
    </div>
  );
};

// 解析分节内容
function parseSections(content: string): Section[] {
  const sections: Section[] = [];
  const lines = content.split('\n');
  let currentSection: Section | null = null;

  for (const line of lines) {
    if (line.startsWith('## ')) {
      if (currentSection) sections.push(currentSection);
      currentSection = {
        type: getSectionType(line),
        title: line.replace('## ', ''),
        content: '',
        items: []
      };
    } else if (currentSection) {
      currentSection.content += line + '\n';
    }
  }

  if (currentSection) sections.push(currentSection);
  return sections;
}

function getSectionType(title: string): string {
  if (title.includes('话术')) return 'script';
  if (title.includes('策略')) return 'strategy';
  if (title.includes('数据')) return 'data';
  if (title.includes('确认')) return 'todo';
  if (title.includes('行动')) return 'action';
  return 'general';
}
```

#### 20.2.4 流式响应Hook

```typescript
// hooks/useStreaming.ts
import { useState, useCallback, useRef } from 'react';

export const useStreaming = () => {
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const eventSourceRef = useRef<EventSource | null>(null);

  const startStreaming = useCallback(async (conversationId: string, messageId: string) => {
    setIsStreaming(true);
    setStreamingContent('');

    const eventSource = new EventSource(
      `/api/v1/conversations/${conversationId}/messages/${messageId}/stream`
    );

    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.event_type) {
        case 'agent_start':
          console.log(`Agent started: ${data.agent}`);
          break;
        case 'agent_complete':
          console.log(`Agent completed: ${data.agent} in ${data.duration_ms}ms`);
          break;
        case 'content':
          setStreamingContent(prev => prev + data.chunk);
          break;
        case 'strategy_annotation':
          console.log(`Strategy: ${data.type} - ${data.description}`);
          break;
        case 'complete':
          setIsStreaming(false);
          eventSource.close();
          break;
        case 'error':
          console.error('Streaming error:', data.error);
          setIsStreaming(false);
          eventSource.close();
          break;
      }
    };

    eventSource.onerror = (error) => {
      console.error('EventSource error:', error);
      setIsStreaming(false);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, []);

  const stopStreaming = useCallback(() => {
    eventSourceRef.current?.close();
    setIsStreaming(false);
  }, []);

  return {
    isStreaming,
    streamingContent,
    startStreaming,
    stopStreaming
  };
};
```

#### 20.2.5 Agent执行链路可视化组件

```typescript
// AgentTrace/AgentTracePanel.tsx
import React from 'react';
import { AgentNode } from './AgentNode';
import { AgentTrace } from '../../types/agent';

interface AgentTracePanelProps {
  trace: AgentTrace;
}

export const AgentTracePanel: React.FC<AgentTracePanelProps> = ({ trace }) => {
  const totalDuration = trace.executed_agents.reduce(
    (sum, agent) => sum + agent.duration_ms, 0
  );

  return (
    <div className="agent-trace-panel">
      <div className="trace-header">
        <h3>Agent执行链路</h3>
        <span className="trace-duration">总耗时: {(totalDuration / 1000).toFixed(1)}s</span>
      </div>

      <div className="trace-timeline">
        {/* 意图识别节点 */}
        <div className="trace-node intent-node">
          <div className="node-icon">🎯</div>
          <div className="node-info">
            <span className="node-name">意图识别</span>
            <span className="node-detail">
              {trace.intent.domain}/{trace.intent.intent} ({(trace.intent.confidence * 100).toFixed(0)}%)
            </span>
          </div>
        </div>

        {/* 执行阶段分组 */}
        {groupAgentsByPhase(trace.executed_agents).map((phase, phaseIndex) => (
          <div key={phaseIndex} className={`trace-phase phase-${phase.type}`}>
            <div className="phase-label">{phase.label}</div>
            <div className="phase-agents">
              {phase.agents.map((agent, agentIndex) => (
                <AgentNode 
                  key={agentIndex}
                  agent={agent}
                  isParallel={phase.type === 'parallel'}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="trace-footer">
        <button className="trace-action">查看详细日志</button>
        <button className="trace-action">查看知识引用</button>
      </div>
    </div>
  );
};

// 按执行阶段分组Agent
function groupAgentsByPhase(agents: ExecutedAgent[]): AgentPhase[] {
  const phases: AgentPhase[] = [];
  let currentPhase: AgentPhase | null = null;

  for (const agent of agents) {
    if (!currentPhase || currentPhase.type !== agent.execution_mode) {
      if (currentPhase) phases.push(currentPhase);
      currentPhase = {
        type: agent.execution_mode,
        label: getPhaseLabel(agent.execution_mode),
        agents: []
      };
    }
    currentPhase.agents.push(agent);
  }

  if (currentPhase) phases.push(currentPhase);
  return phases;
}

function getPhaseLabel(mode: string): string {
  const labels: Record<string, string> = {
    'parallel': '并行执行',
    'serial': '串行执行',
    'supervisory': '监督执行'
  };
  return labels[mode] || '执行';
}
```

### 20.3 样式设计（CSS Modules）

```css
/* ChatContainer.module.css */
.chat-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f7fa;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}

.chat-main {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.chat-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.trace-panel {
  width: 380px;
  background: #fff;
  border-left: 1px solid #e8e8e8;
  overflow-y: auto;
}

/* StructuredMessage.module.css */
.structured-message {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.section {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
}

.section:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a1a;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-script .section-title::before {
  content: '💬';
}

.section-strategy .section-title::before {
  content: '📋';
}

.section-data .section-title::before {
  content: '📊';
}

.section-todo .section-title::before {
  content: '☑️';
}

.section-action .section-title::before {
  content: '🎯';
}

.script-box {
  background: #f6f8fa;
  border-radius: 8px;
  padding: 12px;
  position: relative;
}

.script-box pre {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-size: 13px;
  line-height: 1.6;
  color: #333;
}

.copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 4px 12px;
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.copy-btn:hover {
  background: #1890ff;
  color: #fff;
  border-color: #1890ff;
}

/* AgentTrace.module.css */
.agent-trace-panel {
  padding: 16px;
}

.trace-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.trace-timeline {
  position: relative;
}

.trace-timeline::before {
  content: '';
  position: absolute;
  left: 20px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #e8e8e8;
}

.trace-node {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 0;
  position: relative;
}

.node-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid #1890ff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  z-index: 1;
}

.node-info {
  flex: 1;
}

.node-name {
  display: block;
  font-weight: 500;
  color: #1a1a1a;
  font-size: 13px;
}

.node-detail {
  display: block;
  font-size: 12px;
  color: #666;
  margin-top: 4px;
}

.trace-phase {
  margin: 16px 0;
  padding: 12px;
  background: #f6f8fa;
  border-radius: 8px;
}

.phase-label {
  font-size: 12px;
  color: #666;
  margin-bottom: 8px;
  font-weight: 500;
}

.phase-agents {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.phase-parallel .phase-agents {
  flex-direction: row;
  flex-wrap: wrap;
}
```

---

## 二十一、CI/CD 流水线设计

### 21.1 流水线架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     CI/CD 流水线                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [代码提交]                                                      │
│      │                                                           │
│      ▼                                                           │
│  ┌──────────────┐                                               │
│  │  代码扫描     │  SonarQube + ESLint + Black                   │
│  │  安全检查     │  Snyk + Trivy                                 │
│  └──────────────┘                                               │
│      │                                                           │
│      ▼                                                           │
│  ┌──────────────┐                                               │
│  │  单元测试     │  Jest (前端) + Pytest (后端)                   │
│  │  覆盖率检查   │  >80%                                         │
│  └──────────────┘                                               │
│      │                                                           │
│      ▼                                                           │
│  ┌──────────────┐                                               │
│  │  构建镜像     │  Docker Buildx                                │
│  │  镜像扫描     │  Trivy + Clair                                │
│  └──────────────┘                                               │
│      │                                                           │
│      ▼                                                           │
│  ┌──────────────┐                                               │
│  │  集成测试     │  Postman/Newman + Robot Framework            │
│  │  端到端测试   │  Cypress + Playwright                         │
│  └──────────────┘                                               │
│      │                                                           │
│      ▼                                                           │
│  ┌──────────────┐                                               │
│  │  部署到测试   │  Helm → K8s Test集群                         │
│  │  性能测试     │  k6 + Locust                                  │
│  └──────────────┘                                               │
│      │                                                           │
│      ▼                                                           │
│  ┌──────────────┐                                               │
│  │  人工审核     │  产品经理 + 技术负责人                          │
│  └──────────────┘                                               │
│      │                                                           │
│      ▼                                                           │
│  ┌──────────────┐                                               │
│  │  部署到生产   │  Helm → K8s Prod集群 (金丝雀发布)              │
│  │  监控验证     │  Prometheus + Grafana                         │
│  └──────────────┘                                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 21.2 GitLab CI配置

```yaml
# .gitlab-ci.yml
stages:
  - validate
  - test
  - build
  - integration
  - deploy
  - verify

variables:
  DOCKER_REGISTRY: "registry.example.com"
  KUBE_NAMESPACE_TEST: "sales-brain-test"
  KUBE_NAMESPACE_PROD: "sales-brain-prod"
  HELM_CHART_PATH: "./helm/sales-brain"

# ========== 代码验证阶段 ==========
code_lint:
  stage: validate
  image: node:18
  script:
    - npm ci
    - npm run lint
    - npm run type-check
  only:
    - merge_requests
    - main

security_scan:
  stage: validate
  image: snyk/snyk:node
  script:
    - snyk test --severity-threshold=high
    - snyk code test
  only:
    - merge_requests
    - main

# ========== 测试阶段 ==========
unit_test_frontend:
  stage: test
  image: node:18
  script:
    - npm ci
    - npm run test:unit -- --coverage
    - npm run test:unit -- --coverage --coverageReporters=text-summary
  coverage: '/All files[^|]*\|[^|]*\s+([\d\.]+)/'
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage/cobertura-coverage.xml
    paths:
      - coverage/
  only:
    - merge_requests
    - main

unit_test_backend:
  stage: test
  image: python:3.11
  services:
    - neo4j:5.0
    - mysql:8.0
    - redis:7.0
  script:
    - pip install -r requirements.txt
    - pip install pytest pytest-cov
    - pytest --cov=app --cov-report=xml --cov-report=term
  coverage: '/TOTAL.*\s+(\d+%)$/'
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
  only:
    - merge_requests
    - main

# ========== 构建阶段 ==========
build_images:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  parallel:
    matrix:
      - SERVICE: [api-gateway, master-agent, agent-product, agent-customer, 
                  agent-lead, agent-opportunity, agent-script, agent-quality]
  script:
    - docker build -t $DOCKER_REGISTRY/sales-brain/${SERVICE}:${CI_COMMIT_SHA} 
                   -f ./services/${SERVICE}/Dockerfile ./services/${SERVICE}
    - docker push $DOCKER_REGISTRY/sales-brain/${SERVICE}:${CI_COMMIT_SHA}
    - docker tag $DOCKER_REGISTRY/sales-brain/${SERVICE}:${CI_COMMIT_SHA} 
                 $DOCKER_REGISTRY/sales-brain/${SERVICE}:latest
    - docker push $DOCKER_REGISTRY/sales-brain/${SERVICE}:latest
  only:
    - main

scan_images:
  stage: build
  image: aquasec/trivy:latest
  script:
    - trivy image --severity HIGH,CRITICAL 
                  --exit-code 1 
                  $DOCKER_REGISTRY/sales-brain/master-agent:${CI_COMMIT_SHA}
  only:
    - main

# ========== 集成测试阶段 ==========
integration_test:
  stage: integration
  image: postman/newman:latest
  script:
    - newman run ./tests/api/collection.json 
               -e ./tests/api/environment.json 
               --reporters cli,junit,html
               --reporter-junit-export newman-report.xml
               --reporter-html-export newman-report.html
  artifacts:
    reports:
      junit: newman-report.xml
    paths:
      - newman-report.html
  only:
    - main

e2e_test:
  stage: integration
  image: cypress/included:latest
  script:
    - npm ci
    - npm run cypress:run
  artifacts:
    paths:
      - cypress/videos/
      - cypress/screenshots/
  only:
    - main

# ========== 部署阶段 ==========
deploy_test:
  stage: deploy
  image: bitnami/kubectl:latest
  script:
    - helm upgrade --install sales-brain $HELM_CHART_PATH 
                 --namespace $KUBE_NAMESPACE_TEST 
                 --set image.tag=${CI_COMMIT_SHA}
                 --set environment=test
                 --wait --timeout 10m
  environment:
    name: test
    url: https://sales-brain-test.example.com
  only:
    - main

deploy_prod:
  stage: deploy
  image: bitnami/kubectl:latest
  script:
    - helm upgrade --install sales-brain $HELM_CHART_PATH 
                 --namespace $KUBE_NAMESPACE_PROD 
                 --set image.tag=${CI_COMMIT_SHA}
                 --set environment=production
                 --values $HELM_CHART_PATH/values-production.yaml
                 --wait --timeout 10m
    # 金丝雀发布：先部署10%流量
    - kubectl patch deployment master-agent 
            -n $KUBE_NAMESPACE_PROD 
            -p '{"spec":{"strategy":{"type":"RollingUpdate","rollingUpdate":{"maxSurge":"10%","maxUnavailable":"0"}}}}'
  environment:
    name: production
    url: https://sales-brain.example.com
  when: manual
  only:
    - main

# ========== 验证阶段 ==========
smoke_test:
  stage: verify
  image: curlimages/curl:latest
  script:
    - curl -f https://sales-brain-test.example.com/health || exit 1
    - curl -f https://sales-brain-test.example.com/metrics || exit 1
  only:
    - main

performance_test:
  stage: verify
  image: grafana/k6:latest
  script:
    - k6 run --out influxdb=http://influxdb:8086/k6 
             ./tests/performance/load_test.js
  only:
    - main
    - schedules
```

### 21.3 Helm Chart配置

```yaml
# helm/sales-brain/Chart.yaml
apiVersion: v2
name: sales-brain
description: 数字分身Agent系统
type: application
version: 1.0.0
appVersion: "1.0.0"
dependencies:
  - name: redis
    version: 17.x.x
    repository: https://charts.bitnami.com/bitnami
    condition: redis.enabled
  - name: kafka
    version: 22.x.x
    repository: https://charts.bitnami.com/bitnami
    condition: kafka.enabled
```

```yaml
# helm/sales-brain/values.yaml
# 全局配置
global:
  environment: development
  imageRegistry: "registry.example.com"
  imageTag: "latest"

# API网关
apiGateway:
  enabled: true
  replicas: 2
  image:
    repository: sales-brain/api-gateway
    tag: "{{ .Values.global.imageTag }}"
  resources:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: 2000m
      memory: 2Gi
  service:
    type: ClusterIP
    port: 8080
  ingress:
    enabled: true
    className: nginx
    hosts:
      - host: api.sales-brain.example.com
        paths:
          - path: /
            pathType: Prefix

# Master Agent
masterAgent:
  enabled: true
  replicas: 3
  image:
    repository: sales-brain/master-agent
    tag: "{{ .Values.global.imageTag }}"
  resources:
    requests:
      cpu: 1000m
      memory: 2Gi
    limits:
      cpu: 4000m
      memory: 8Gi
  env:
    - name: LLM_API_KEY
      valueFrom:
        secretKeyRef:
          name: sales-brain-secrets
          key: llm-api-key
    - name: INTENT_CLASSIFIER_MODEL
      value: "intent-v2.1"

# 产品专家Agent
agentProduct:
  enabled: true
  replicas: 2
  image:
    repository: sales-brain/agent-product
    tag: "{{ .Values.global.imageTag }}"
  resources:
    requests:
      cpu: 1000m
      memory: 2Gi
    limits:
      cpu: 4000m
      memory: 8Gi

# 其他Agent配置类似...

# 数据库配置
database:
  mysql:
    enabled: true
    host: "mysql.sales-brain.svc.cluster.local"
    port: 3306
    database: "sales_brain"
    username: "sales_brain"
    passwordSecret: "sales-brain-secrets"
    passwordKey: "db-password"

  neo4j:
    enabled: true
    host: "neo4j.sales-brain.svc.cluster.local"
    port: 7687
    username: "neo4j"
    passwordSecret: "sales-brain-secrets"
    passwordKey: "neo4j-password"

  milvus:
    enabled: true
    host: "milvus.sales-brain.svc.cluster.local"
    port: 19530

# 缓存配置
redis:
  enabled: true
  architecture: replication
  auth:
    enabled: true
    existingSecret: "sales-brain-secrets"
    existingSecretPasswordKey: "redis-password"

# 消息队列
kafka:
  enabled: true
  replicas: 3
  auth:
    clientProtocol: sasl
    sasl:
      jaas:
        clientUsers:
          - sales-brain
        clientPasswords:
          - "{{ .Values.global.kafkaPassword }}"
```

---

## 二十二、成本估算

### 22.1 基础设施成本（月度）

| 资源 | 规格 | 数量 | 单价(元/月) | 小计(元/月) |
|------|------|------|-------------|-------------|
| **云服务器** | | | | |
| K8s节点(应用) | 8C16G | 6台 | 1,200 | 7,200 |
| K8s节点(数据库) | 16C32G | 3台 | 2,400 | 7,200 |
| 负载均衡 | ALB | 2个 | 500 | 1,000 |
| **数据库** | | | | |
| MySQL RDS | 8C16G 500G SSD | 1套 | 3,500 | 3,500 |
| Neo4j | 8C16G 500G SSD | 1套 | 4,000 | 4,000 |
| Milvus | 8C16G 500G SSD | 1套 | 3,500 | 3,500 |
| Redis | 4C8G 集群版 | 1套 | 1,500 | 1,500 |
| **存储** | | | | |
| 对象存储 | 标准存储 2TB | 1 | 200/TB | 400 |
| 备份存储 | 低频存储 5TB | 1 | 120/TB | 600 |
| **网络** | | | | |
| 公网带宽 | 100Mbps | 1 | 3,000 | 3,000 |
| CDN | 流量包 500GB | 1 | 500 | 500 |
| **监控** | | | | |
| Prometheus+Grafana | 托管版 | 1套 | 800 | 800 |
| 日志服务 | 100GB/日 | 1 | 1,200 | 1,200 |
| **安全** | | | | |
| WAF | 高级版 | 1 | 1,500 | 1,500 |
| SSL证书 | 通配符 | 1 | 500 | 500 |
| **LLM API** | | | | |
| GPT-4 API | 按Token计费 | - | - | 5,000 |
| Embedding API | 按Token计费 | - | - | 1,000 |
| **总计** | | | | **42,900** |

### 22.2 人力成本（月度）

| 角色 | 人数 | 单价(元/月) | 小计(元/月) |
|------|------|-------------|-------------|
| 架构师 | 1 | 50,000 | 50,000 |
| 后端开发(Agent) | 3 | 35,000 | 105,000 |
| 后端开发(数据) | 2 | 30,000 | 60,000 |
| 前端开发 | 2 | 30,000 | 60,000 |
| 算法工程师 | 2 | 40,000 | 80,000 |
| DevOps工程师 | 1 | 35,000 | 35,000 |
| 测试工程师 | 1 | 25,000 | 25,000 |
| 产品经理 | 1 | 35,000 | 35,000 |
| **总计** | **13** | | **450,000** |

### 22.3 总成本估算

| 阶段 | 时间 | 基础设施(元/月) | 人力(元/月) | 其他(元/月) | 阶段总计 |
|------|------|----------------|-------------|-------------|----------|
| **Phase 1** | M1-M2 | 42,900 | 450,000 | 20,000 | 1,025,800 |
| **Phase 2** | M3-M4 | 45,000 | 400,000 | 15,000 | 920,000 |
| **Phase 3** | M5-M6 | 48,000 | 350,000 | 10,000 | 816,000 |
| **Phase 4** | M7-M8 | 50,000 | 300,000 | 10,000 | 720,000 |
| **Phase 5** | M9-M12 | 55,000 | 250,000 | 15,000 | 1,280,000 |
| **运维期** | M13+ | 55,000 | 150,000 | 10,000 | 215,000/月 |

**项目总投入（首年）**: 约 **476万元**
**年度运维成本**: 约 **258万元/年**

### 22.4 ROI分析

| 收益项 | 计算方式 | 年度收益(万元) |
|--------|----------|---------------|
| 新人培养成本降低 | 10人 × 3个月 × 1.5万/月 | 45 |
| 销售效率提升 | 50销售 × 20%效率提升 × 人均产出100万 | 1,000 |
| 客户转化率提升 | 1000线索 × 5%提升 × 客单价50万 | 2,500 |
| 人才流失降低 | 减少5人离职 × 人均替换成本20万 | 100 |
| 管理效率提升 | 管理层时间节省 × 管理成本 | 200 |
| **年度总收益** | | **3,845** |

**ROI = (3,845 - 476) / 476 × 100% = 707%**

---

## 二十三、数据流详细设计

### 23.1 核心数据流

```
┌─────────────────────────────────────────────────────────────────┐
│                     数据流全景图                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    │
│  │  用户输入 │--->│ 意图识别 │--->│ 任务分解 │--->│ Agent调度│    │
│  │         │    │         │    │         │    │         │    │
│  │ 文本/语音│    │ NLP模型  │    │ DAG生成  │    │ 路由决策 │    │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘    │
│       │              │              │              │            │
│       │              │              │              │            │
│       ▼              ▼              ▼              ▼            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    记忆检索层                             │   │
│  │  会话记忆 │ 短期记忆 │ 长期记忆 │ 组织记忆              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Agent执行层                            │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │   │
│  │  │ Agent 1 │  │ Agent 2 │  │ Agent 3 │  │ Agent N │   │   │
│  │  │ 执行中   │  │ 执行中   │  │ 执行中   │  │ 执行中   │   │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │   │
│  │                              │                          │   │
│  │                              ▼                          │   │
│  │                    ┌─────────────┐                      │   │
│  │                    │  结果聚合    │                      │   │
│  │                    │  + 冲突解决  │                      │   │
│  │                    └─────────────┘                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    知识检索层                             │   │
│  │  向量检索 │ 图谱查询 │ 结构化查询 │ 全文检索              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    响应生成层                             │   │
│  │  文本合成 │ 结构化输出 │ 卡片生成 │ 建议行动              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    输出层                                 │   │
│  │  文本回复 │ 数据卡片 │ 快捷操作 │ 追踪链路              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 23.2 数据流时序图

```
用户          MasterAgent    IntentService    TaskService    AgentPool    KnowledgeService    ResponseService
 │                │                │                │              │                │                │
 │--发送消息----->│                │                │              │                │                │
 │                │--识别意图---->│                │              │                │                │
 │                │                │--返回意图------│              │                │                │
 │                │--分解任务---------------------->│              │                │                │
 │                │                │                │--创建DAG--->│                │                │
 │                │                │                │              │--并行执行Agent-->│                │
 │                │                │                │              │                │--检索知识------>│
 │                │                │                │              │                │<--返回知识------│
 │                │                │                │              │<--Agent完成-----│                │
 │                │                │                │<--任务完成----│                │                │
 │                │                │                │              │                │                │
 │                │--聚合结果-------------------------------------->│                │                │
 │                │                │                │              │                │                │
 │                │--生成响应--------------------------------------->│                │                │
 │                │                │                │              │                │                │
 │<--返回结果-----│                │                │              │                │                │
 │                │                │                │              │                │                │
```

---

## 二十四、Agent状态机

### 24.1 Agent生命周期状态机

```
┌─────────────────────────────────────────────────────────────────┐
│                     Agent状态机                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                         ┌─────────┐                             │
│                         │  初始化  │                             │
│                         │ (Init)   │                             │
│                         └────┬────┘                             │
│                              │ 注册到Master                      │
│                              ▼                                   │
│                         ┌─────────┐                             │
│                         │  空闲   │◄────────────────────────┐    │
│                         │ (Idle)  │                         │    │
│                         └────┬────┘                         │    │
│                              │ 接收任务                       │    │
│                              ▼                                │    │
│                         ┌─────────┐                          │    │
│                         │  执行中  │                          │    │
│                         │(Running)│                          │    │
│                         └────┬────┘                          │    │
│                              │                               │    │
│              ┌──────────────┼──────────────┐              │    │
│              │              │              │              │    │
│              ▼              ▼              ▼              │    │
│        ┌─────────┐    ┌─────────┐    ┌─────────┐         │    │
│        │  成功   │    │  失败   │    │  超时   │         │    │
│        │(Success)│    │(Failure)│    │(Timeout)│         │    │
│        └────┬────┘    └────┬────┘    └────┬────┘         │    │
│             │              │              │              │    │
│             │              │              │              │    │
│             ▼              ▼              ▼              │    │
│        ┌─────────┐    ┌─────────┐    ┌─────────┐         │    │
│        │  完成   │    │  重试   │    │  降级   │         │    │
│        │(Complete)│   │ (Retry) │    │(Fallback)│        │    │
│        └────┬────┘    └────┬────┘    └────┬────┘         │    │
│             │              │              │              │    │
│             └──────────────┼──────────────┘              │    │
│                            │                             │    │
│                            ▼                             │    │
│                      ┌─────────┐                         │    │
│                      │  空闲   │─────────────────────────┘    │
│                      │ (Idle)  │  任务完成，回归空闲           │
│                      └─────────┘                             │
│                                                                  │
│  异常状态：                                                       │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐                    │
│  │  熔断   │    │  停用   │    │  销毁   │                    │
│  │(Circuit)│    │(Disabled)│   │(Destroyed)│                  │
│  └─────────┘    └─────────┘    └─────────┘                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 24.2 任务状态转换

| 当前状态 | 触发事件 | 下一状态 | 动作 |
|----------|----------|----------|------|
| PENDING | Master分配任务 | RUNNING | 加载上下文，开始执行 |
| RUNNING | 执行成功 | SUCCESS | 返回结果，释放资源 |
| RUNNING | 执行失败（可重试） | RETRYING | 增加重试计数，延迟重试 |
| RUNNING | 执行失败（不可重试） | FAILED | 记录错误，通知Master |
| RUNNING | 超时 | TIMEOUT | 取消执行，返回超时错误 |
| RETRYING | 重试成功 | SUCCESS | 返回结果 |
| RETRYING | 重试耗尽 | FAILED | 返回最终错误 |
| SUCCESS | 质检不通过 | CORRECTING | 修正输出 |
| CORRECTING | 修正成功 | SUCCESS | 返回修正后结果 |
| FAILED | Master触发降级 | FALLBACK | 切换到备用Agent |

---

## 二十五、错误处理机制

### 25.1 错误分类与处理策略

| 错误类型 | 示例 | 处理策略 | 用户感知 |
|----------|------|----------|----------|
| **业务错误** | 产品不存在 | 返回明确错误信息+建议 | "该产品不存在，您是否指的是XXX？" |
| **知识错误** | 知识库无匹配 | 降级到通用回答+标记 | "暂时没有找到相关信息，建议咨询产品经理" |
| **系统错误** | Agent崩溃 | 自动重试+切换备用 | "正在重新处理，请稍候..." |
| **超时错误** | 响应>10s | 返回部分结果+异步通知 | "已收到您的问题，正在深度分析中..." |
| **权限错误** | 访问敏感数据 | 脱敏返回+记录审计 | "您当前权限可查看指导价，底价请联系主管" |
| **幻觉错误** | AI编造事实 | 事实核查拦截+人工复核 | "该信息需要进一步核实，建议确认后再回复客户" |

### 25.2 错误恢复流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     错误恢复流程                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [错误发生]                                                      │
│      │                                                           │
│      ▼                                                           │
│  ┌──────────────┐                                               │
│  │  错误分类     │  业务/知识/系统/超时/权限/幻觉                │
│  └──────────────┘                                               │
│      │                                                           │
│      ▼                                                           │
│  ┌──────────────┐                                               │
│  │  自动恢复     │                                               │
│  │  • 重试(最多3次)                                             │
│  │  • 切换备用Agent                                             │
│  │  • 降级到简化模式                                            │
│  │  • 返回缓存结果                                              │
│  └──────────────┘                                               │
│      │                                                           │
│      ▼                                                           │
│  ┌──────────────┐                                               │
│  │  恢复成功？   │                                               │
│  └──────────────┘                                               │
│      │                                                           │
│   是 /   \ 否                                                    │
│     /     \                                                      │
│    ▼       ▼                                                     │
│ ┌─────┐  ┌──────────────┐                                       │
│ │返回 │  │  人工介入     │                                       │
│ │结果 │  │  • 通知运维   │                                       │
│ └─────┘  │  • 记录工单   │                                       │
│          │  • 提供降级方案│                                       │
│          └──────────────┘                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

> **深度补充文档结束**
>
> 本文档补充了Cypher查询优化、前端组件代码实现、CI/CD流水线、成本估算、数据流设计、Agent状态机和错误处理机制等深度技术内容。


---

## 二十六、Prompt 工程设计

### 26.1 Master Agent System Prompt

```
你是数字分身系统的核心调度Agent（Master Agent），负责理解销售人员的请求，
调度合适的专业Agent协同工作，并整合输出高质量的销售辅助内容。

## 核心职责
1. 意图识别：准确理解用户的真实需求，拆解为可执行的子任务
2. Agent调度：根据任务类型，选择最合适的Agent组合
3. 结果聚合：整合多个Agent的输出，确保逻辑一致、内容完整
4. 质量把控：监督输出质量，发现冲突时启动仲裁机制

## 调度原则
- 简单查询（如查库存）：直接调度单一Agent
- 复杂场景（如价格异议）：并行调度多个Agent，再串行生成最终回复
- 高风险场景（如报价、合同）：必须经质检Agent审核
- 低置信度场景：主动请求用户澄清，不盲目回答

## 输出格式规范
所有最终输出必须包含以下结构：
1. 【建议话术/方案】- 直接可用的内容
2. 【策略注解】- 解释为什么这样回复，用了什么策略
3. 【数据支撑】- 引用的事实和数据，标注来源
4. 【待确认信息】- 需要向客户确认的关键问题
5. 【下一步行动】- 具体的后续行动建议
6. 【风险提示】- 潜在风险和应对建议

## 安全约束
- 绝不泄露底价、成本价等敏感信息（除非用户有相应权限）
- 不编造事实，不确定的内容标注"待确认"
- 不替用户做最终决策，只提供参考建议
- 涉及合规风险的内容（如承诺、保证）必须标注风险提示
```

### 26.2 产品专家Agent System Prompt

```
你是产品专家Agent，精通企业所有产品的技术参数、性能特点、应用场景和竞争优势。
你的任务是为销售提供准确、专业的产品信息支持。

## 核心能力
1. 产品检索：根据客户需求快速找到匹配的产品
2. 参数对比：多产品横向对比，突出差异和优势
3. 方案推荐：基于应用场景推荐最优配置
4. 配件关联：通过知识图谱推荐兼容配件和耗材
5. 竞品分析：客观对比竞品优劣势，提供应对策略

## 知识来源优先级
1. ERP实时数据（库存、价格）- 最高优先级
2. 产品知识库（技术文档、手册）
3. 案例库（实际应用效果）
4. 竞品数据库

## 输出规范
- 技术参数必须准确，引用具体数值
- 对比必须客观，不贬低竞品
- 推荐必须说明理由，关联客户需求
- 库存和价格必须标注数据来源和时间

## 特殊约束
- 指导价对外公开，底价和成本价仅对授权人员显示
- 停产产品必须标注替代型号
- 缺货产品必须提供预计到货时间
```

### 26.3 话术专家Agent System Prompt

```
你是话术专家Agent，擅长将技术语言转化为客户价值语言，
设计有说服力的销售话术和谈判策略。

## 核心能力
1. 异议处理：将客户异议转化为展示价值的机会
2. 话术润色：将生硬的技术参数转化为客户关心的利益点
3. 邮件生成：撰写专业、有吸引力的销售邮件
4. 谈判辅助：提供谈判策略和底线提醒
5. 角色扮演：模拟客户场景，帮助销售预演

## 话术设计原则
1. FAB法则：Feature（特性）-> Advantage（优势）-> Benefit（利益）
2. 价值锚定：先建立价值认知，再讨论价格
3. 社会认同：引用标杆客户案例增强说服力
4. 稀缺性：合理利用库存紧张、促销截止等稀缺信息
5. 选择架构：提供2-3个方案，引导客户做选择而非是否购买

## 异议处理策略库
- 价格异议：价值重构、总拥有成本、分期方案、增值服务
- 品牌异议：案例证明、本地化服务、定制化能力
- 功能异议：现场演示、试用方案、功能路线图
- 交期异议：现货优势、加急方案、替代方案
- 决策异议：决策人影响、ROI计算、风险评估

## 输出规范
- 提供2-3个版本的话术（简洁版/详细版/正式版）
- 每个话术附策略注解，解释为什么这么设计
- 标注需要确认的信息和潜在风险
- 邮件必须包含主题行、正文、签名完整格式
```

### 26.4 质检专家Agent System Prompt

```
你是质检专家Agent，负责审核其他Agent的输出质量，
确保事实准确、合规安全、表达专业。

## 审核维度
1. 事实核查：检查技术参数、价格、库存等事实性内容
2. 合规检查：检查是否违反公司政策、行业规范
3. 逻辑检查：检查推理过程是否合理，有无逻辑漏洞
4. 完整性检查：检查是否遗漏关键信息
5. 安全性检查：检查是否泄露敏感信息

## 审核标准
- 事实错误：零容忍，必须纠正
- 合规风险：高风险必须拦截，中风险必须标注
- 逻辑问题：必须指出并建议修正
- 遗漏信息：必须列出待确认项

## 评分标准
- 准确性（40%）：事实正确、数据准确
- 完整性（20%）：信息全面、无遗漏
- 合规性（20%）：符合政策、无风险
- 专业性（20%）：表达专业、逻辑清晰

## 输出格式
```
审核结果：[通过/不通过/需修正]
质量评分：X.XX（准确性X.X + 完整性X.X + 合规性X.X + 专业性X.X）

问题清单：
1. [类型] [严重程度] [问题描述] [修正建议]

修正建议：
[具体的修正内容]
```

## 特殊约束
- 不通过的内容必须给出具体修正建议
- 涉及敏感信息泄露的必须立即拦截并告警
- 不确定的内容必须标注"需人工复核"
```

### 26.5 Few-Shot示例设计

#### 价格异议处理示例

```
## 示例1：客户说"太贵了"

用户输入：客户觉得我们850Pro价格太贵了，比竞品高20%，我该怎么回？

产品专家输出：
- 850Pro指导价：28.5万
- 竞品M-V500指导价：45万（实际比我们贵60%）
- 850Pro核心优势：12000转直结主轴、米汉纳铸铁床身、24小时售后
- 库存：5台现货，7天交货

客户专家输出：
- 客户：广州山河科技，汽车零部件行业，A类客户
- 历史采购：2025年采购2台850Pro，满意度5星
- 决策人：王建国（生产总监，技术决策者）

话术专家输出：
【建议话术】
王总，非常感谢您这么坦诚地反馈。确实，如果单看报价，我们的850Pro可能不是
市场上最便宜的。但客户买的不是一台机器，而是一套能稳定赚钱的生产力解决方案。

我给您看一组数据：在同样的中低速强力切削条件下，咱们的850Pro扭矩输出比
日系M牌竞品高出约15%。这意味着在加工汽车零部件时，我们的机床吃刀更深、
效率更高，能有效缩短单个零件的加工时间，直接提升您的产能。

另外，目前这款850Pro我们有5台现货。您知道，现在供应链不稳定，很多品牌
交期要3-6个月。您选择我们，设备下周就能到位安装，快速投产，早一天开机
就早一天产生利润。

所以，我建议我们可以不算"单价"，而是算一算"单件成本"和"投资回报"。

【策略注解】
1. 价值重构与转移：将对话从"为什么贵"转向"贵得值"
2. 数据锚定：用15%扭矩优势建立技术可信度
3. 稀缺性：5台现货创造紧迫感
4. 总拥有成本：引导客户计算长期收益而非短期价格

【待确认信息】
- 客户所指的"竞品"具体品牌和型号？
- 客户主要用它加工什么材料？
```

---

## 二十七、多租户架构设计

### 27.1 租户隔离策略

| 隔离级别 | 实现方式 | 适用场景 | 成本 |
|----------|----------|----------|------|
| **物理隔离** | 独立K8s集群+独立数据库 | 大型集团客户 | 高 |
| **逻辑隔离** | 共享集群+Schema隔离 | 中型企业客户 | 中 |
| **行级隔离** | 共享Schema+tenant_id字段 | 中小型企业 | 低 |

### 27.2 推荐方案：Schema隔离

```sql
-- 为每个租户创建独立Schema
CREATE SCHEMA tenant_001;
CREATE SCHEMA tenant_002;

-- 租户表结构相同，数据完全隔离
tenant_001.products
tenant_001.customers
tenant_001.orders

tenant_002.products
tenant_002.customers
tenant_002.orders
```

### 27.3 租户上下文传递

```python
class TenantContext:
    def __init__(self):
        self._tenant_id = None

    def set_tenant(self, tenant_id: str):
        self._tenant_id = tenant_id
        # 设置数据库连接Schema
        db.set_search_path(f"tenant_{tenant_id}")
        # 设置知识图谱命名空间
        kg.set_namespace(f"tenant_{tenant_id}")
        # 设置缓存前缀
        cache.set_prefix(f"tenant:{tenant_id}:")

    def get_tenant(self) -> str:
        return self._tenant_id

    def clear(self):
        self._tenant_id = None

# 在API入口设置租户上下文
@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Missing tenant ID")

    tenant_context.set_tenant(tenant_id)

    try:
        response = await call_next(request)
        return response
    finally:
        tenant_context.clear()
```

### 27.4 租户资源配额

| 资源类型 | 免费版 | 专业版 | 企业版 |
|----------|--------|--------|--------|
| 用户数 | 5 | 50 | 无限 |
| 消息数/月 | 1,000 | 50,000 | 无限 |
| 知识库容量 | 1GB | 50GB | 500GB |
| Agent数量 | 3 | 6 | 自定义 |
| API调用/月 | 10,000 | 500,000 | 无限 |
| 数据保留期 | 30天 | 1年 | 永久 |
| 定制开发 | 不支持 | 有限支持 | 全面支持 |

---

## 二十八、性能基准测试方案

### 28.1 测试环境

| 组件 | 配置 | 数量 |
|------|------|------|
| 应用服务器 | 8C16G | 3台 |
| 数据库 | 8C16G 500G SSD | 1套 |
| 负载生成器 | 4C8G | 2台 |

### 28.2 基准测试用例

#### 28.2.1 单用户延迟测试

| 场景 | 输入 | 预期P50 | 预期P99 |
|------|------|---------|---------|
| 简单查询 | "850Pro参数" | <500ms | <800ms |
| 单Agent任务 | "查库存" | <1s | <2s |
| 多Agent并行 | "价格异议处理" | <2s | <5s |
| 复杂多轮 | "客户背调+方案推荐" | <3s | <8s |
| 流式响应 | 长文本生成 | 首token<500ms | 完整<10s |

#### 28.2.2 并发吞吐量测试

| 并发用户 | 持续时间 | 目标QPS | 错误率 | 平均响应 |
|----------|----------|---------|--------|----------|
| 10 | 5分钟 | >20 | <0.1% | <2s |
| 50 | 10分钟 | >80 | <0.5% | <3s |
| 100 | 15分钟 | >150 | <1% | <5s |
| 200 | 10分钟 | >250 | <2% | <8s |
| 500 | 5分钟 | >400 | <5% | <15s |

#### 28.2.3 稳定性测试

| 场景 | 持续时间 | 目标 |
|------|----------|------|
| 正常负载 | 72小时 | 无内存泄漏，响应时间稳定 |
| 高低负载交替 | 24小时 | 自动扩缩容正常，无服务中断 |
| 故障注入 | 4小时 | 单点故障不影响整体服务 |

### 28.3 测试脚本示例（k6）

```javascript
// performance_test.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '2m', target: 50 },
    { duration: '5m', target: 50 },
    { duration: '2m', target: 100 },
    { duration: '5m', target: 100 },
    { duration: '2m', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(99)<5000'],
    errors: ['rate<0.05'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'https://api.sales-brain.example.com';
const API_KEY = __ENV.API_KEY;

export default function () {
  const productQuery = {
    content: 'VMC-850Pro的技术参数是什么？',
    content_type: 'text',
  };

  let response = http.post(`${BASE_URL}/v1/conversations/new/messages`,
    JSON.stringify(productQuery),
    {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${API_KEY}`,
      },
    }
  );

  const success = check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 2s': (r) => r.timings.duration < 2000,
    'has content': (r) => JSON.parse(r.body).data.content.length > 0,
  });

  errorRate.add(!success);
  sleep(1);

  const objectionQuery = {
    content: '客户觉得我们850Pro太贵了，比竞品高20%，我该怎么回？',
    content_type: 'text',
    context: {
      customer_id: 'CUST_001',
      product_model: 'VMC-850Pro',
    },
    options: {
      enable_deep_thinking: true,
    },
  };

  response = http.post(`${BASE_URL}/v1/conversations/new/messages`,
    JSON.stringify(objectionQuery),
    {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${API_KEY}`,
      },
    }
  );

  const objectionSuccess = check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 5s': (r) => r.timings.duration < 5000,
    'has agent trace': (r) => JSON.parse(r.body).data.agent_trace !== undefined,
    'has strategy annotation': (r) => 
      JSON.parse(r.body).data.content.includes('【策略注解】'),
  });

  errorRate.add(!objectionSuccess);
  sleep(2);
}
```

---

## 二十九、用户培训计划

### 29.1 培训体系

| 培训对象 | 培训内容 | 培训方式 | 时长 |
|----------|----------|----------|------|
| **销售新人** | 基础功能使用、常见场景操作 | 线上视频+实操练习 | 2小时 |
| **资深销售** | 高级功能、自定义Prompt、数据分析 | 线下工作坊 | 4小时 |
| **销售主管** | 团队管理、数据看板、质检功能 | 1对1培训 | 2小时 |
| **管理员** | 系统配置、知识库管理、权限设置 | 技术文档+远程支持 | 4小时 |

### 29.2 销售新人培训大纲

#### 模块1：认识数字分身（15分钟）
- 什么是数字分身
- 能解决什么问题
- 与ChatGPT的区别

#### 模块2：基础操作（30分钟）
- 界面介绍
- 如何提问（提问技巧）
- 快捷入口使用
- 查看历史对话

#### 模块3：核心场景实操（45分钟）
- 场景1：客户问产品参数怎么回
- 场景2：客户说太贵了怎么回
- 场景3：客户没回我怎么跟进
- 场景4：怎么查客户背景
- 场景5：怎么写跟进邮件

#### 模块4：进阶技巧（20分钟）
- 如何导入聊天记录做质检
- 如何查看Agent执行链路
- 如何反馈问题帮助改进

#### 模块5：实战演练（10分钟）
- 模拟真实客户场景
- 现场操作考核

### 29.3 培训材料清单

| 材料 | 格式 | 用途 |
|------|------|------|
| 快速上手指南 | PDF | 新人入职发放 |
| 场景操作手册 | 在线文档 | 日常查阅 |
| 视频教程 | MP4 | 自学培训 |
| 常见问题FAQ | 在线文档 | 自助解决问题 |
| 最佳实践案例集 | PPT | 团队分享 |
| 月度使用报告 | 自动邮件 | 激励和提醒 |

---

## 三十、竞品分析对比

### 30.1 市场竞品概览

| 竞品 | 定位 | 核心能力 | 价格区间 | 优势 | 劣势 |
|------|------|----------|----------|------|------|
| **Salesforce Einstein** | CRM内置AI | 预测分析、自动化 | $$$ | 生态完整 | 定制化差、中文弱 |
| **Gong.io** | 销售智能 | 通话分析、话术优化 | $$ | 通话分析强 | 无产品知识、无中文 |
| **微软Copilot for Sales** | Office生态 | 邮件生成、CRM集成 | $$ | Office集成 | 通用性强、行业弱 |
| **百度智能云客悦** | 国内通用 | 客服机器人 | $ | 价格低 | 销售场景弱 |
| **科大讯飞AI助手** | 语音交互 | 语音转写、分析 | $$ | 语音强 | 知识图谱弱 |
| **本方案** | 行业专用 | Agent协同+知识图谱 | $$ | 行业深度、中文强 | 品牌知名度待建 |

### 30.2 差异化优势

| 维度 | 本方案 | 通用方案 |
|------|--------|----------|
| **知识深度** | 行业知识图谱，产品关系立体 | 通用向量检索，信息孤立 |
| **Agent协同** | 多Agent专业分工，协同决策 | 单一模型，无专业分工 |
| **数据联动** | 实时ERP/CRM数据 | 静态知识库 |
| **话术策略** | 策略注解+待确认信息 | 直接输出，无解释 |
| **质检闭环** | 自动质检+人工复核 | 无质检机制 |
| **中文场景** | 深度优化中文销售场景 | 通用中文能力 |
| **私有化** | 支持私有化部署 | SaaS为主 |

### 30.3 竞争策略

| 策略 | 具体措施 |
|------|----------|
| **知识壁垒** | 持续积累行业知识图谱，形成数据飞轮 |
| **场景深耕** | 聚焦B2B复杂销售场景，做深做透 |
| **生态集成** | 深度集成主流ERP/CRM，降低切换成本 |
| **标杆客户** | 打造行业标杆案例，形成口碑效应 |
| **成本优势** | 国产化替代，价格低于国外竞品50% |

---

> **最终补充文档结束**
>
> 本文档补充了Prompt工程设计、多租户架构、性能基准测试、用户培训计划和竞品分析对比等内容，
> 形成了完整的数字分身Agent系统技术方案体系。

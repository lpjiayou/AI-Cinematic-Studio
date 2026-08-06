# Application Layer Overview

## 1. 文档定位

本文定义 AI Cinematic Studio V2.3 中 Application Layer 的最小职责与禁止边界。它是 ACS-P1-UI-001 的技术中立知识资产，不定义具体产品界面、UI 组件、API、业务流程、数据模型、存储、Worker、部署方式或实现技术，也不新增或改变 V2.3 模块。

Application Layer 是系统能力的上层消费与交付边界。任何具体 Application Profile、物理目录或实现只有在独立任务明确授权并完成适用评审后才成立。

## 2. Application Layer 职责

Application Layer 只承担以下上层职责：

1. 在获批范围内呈现可观察信息，并接收用户交互所表达的意图。
2. 管理展示所需的 presentation state，确保展示行为与已获批结果、错误和关联上下文一致。
3. 将获批用户意图整理为符合 Application Layer → V5 Core OS 公开契约的 Command Intent，而不规定下游实现步骤。
4. 向 V5 Core OS 提供契约要求的前置条件、授权来源和适用关联标识，并处理公开 Output 与 Error。
5. 隐藏 Application 内部展示细节，不让下层依赖 UI 结构、页面状态或 Application 私有实现。
6. 为职责、契约、验证范围和变更提供可追溯说明，但不以文档替代实现授权或架构批准。

Application Layer 不承担 V5 Core OS、V4 Platform、V3 Render Core、Compute 或 Foundation 的内部职责，也不拥有仅因展示、输入或缓存而接触到的 domain fact。

## 3. Presentation State 与 Domain Fact

### 3.1 Presentation State

Presentation state 是为当前交互与展示服务的非权威状态，例如可见性、当前选择、尚未提交的输入、展示顺序、筛选偏好、加载状态和错误展示状态。它可以帮助 Application 组织界面体验，但不得成为跨层业务判断或权威事实来源。

Presentation state：

- 由 Application Layer 在自身边界内解释；
- 不自动获得数据所有权或跨会话持久化资格；
- 不得编码 V5/V4/V3/Compute 的内部状态机、私有模型或执行步骤；
- 不得通过本地副本、缓存或展示 projection 覆盖公开契约返回的权威语义。

### 3.2 Domain Fact

Domain fact 是由获批数据责任和公开契约定义的权威语义。Identity、Project、Asset、Production、Render、Business 与 Intelligence 只是既有概念数据分类；分类名称本身不创建实体、模块、接口、所有权或存储位置。

Application Layer 可以按获批契约展示或引用 domain fact，但必须：

- 通过 V5 Core OS 的公开契约读取或提交意图，不直接访问 owner 的内部表示或存储；
- 保持来源、适用范围与关联标识可追溯；
- 不因创建、编辑、展示、筛选、缓存或组合视图而宣称拥有该事实；
- 不从 UI 路由、标签、字段或交互推导跨域关系、生命周期状态或写入权限。

Presentation state 与 domain fact 必须保持可区分。将 presentation state 提交为意图并不使其自动成为 domain fact；只有获批下层契约返回的稳定结果才能被 Application 作为公开语义消费。

## 4. 层间关系

### 4.1 与 V5 Core OS 的直接关系

Application Layer 唯一允许的直接下层依赖是 V5 Core OS 的公开契约：

`Application Layer → V5 Core OS`

Application 负责提供符合契约的意图和上下文，并正确消费公开结果与错误；V5 Core OS 负责其公开契约的语义、兼容性、边界验证和内部实现封装。响应、错误或事件沿获批契约返回，不构成 V5 Core OS 对 Application Layer 的反向依赖。

Application 不得把 UI 结构、组件状态或私有对象作为 V5 Core OS 的依赖，也不得把 Command Intent 写成 V4/V3/Compute 的执行计划。

### 4.2 与 V4、V3 和 Compute 的间接关系

Application Layer 与 V4 Platform、V3 Render Core 和 Compute 仅存在经相邻公开契约形成的间接关系：

`Application Layer → V5 Core OS → V4 Platform → V3 Render Core → Compute`

因此 Application Layer：

- 不直接调用、导入、配置或测试 V4 Platform、V3 Render Core 或 Compute 的内部或公开实现；
- 不向这些层发送专属命令、资源参数、存储位置或执行细节；
- 不依赖它们的私有错误、状态、数据结构或生命周期；
- 不以事件、回调、共享文件、共享存储、Worker 或脚本绕过 V5 Core OS。

Compute 与 Foundation 的关系继续由 V2.3 基线约束，Application Layer 不得直接参与或推导该关系的实现。

## 5. 明确禁止

- **UI 不得直接修改 Domain 事实**：用户动作只能形成 Command Intent；本地 presentation state、草稿、缓存和乐观呈现都不是权威事实。
- **UI 不得直接访问存储**：Application Layer 不得直接读写任何抽象或具体存储能力、内部数据访问层或共享持久化状态。
- **UI 不得直接调用 Worker**：Application Layer 不得发现、配置、启动、暂停、重试或控制下层执行实现；“Worker”不构成新的 V2.3 层级或模块。
- **禁止存储职责**：Application Layer 不定义或直接访问 Operational Storage、Object Storage、Vector Storage、Analytics Storage、数据库、对象位置或其他持久化机制，也不声明数据 owner。
- **禁止 Worker 职责**：Application Layer 不创建或拥有后台 Worker、队列消费者、调度器、渲染执行器、计算作业执行器或长期运行服务。
- **禁止跨层职责**：Application Layer 不绕过 V5 Core OS 直连 V4/V3/Compute/Foundation，不导入下层私有实现，不形成反向或循环依赖。
- **禁止实现推导**：本文不批准 UI 组件、API 端点、协议、序列化格式、框架、部署单元、数据模型或技术产品。

## 6. Internal Content Lab 的条件性映射

Internal Content Lab 当前只在 [Phase 1 Production Validation Plan](../12-release/phase-1-production-validation-plan.md) 中被描述为条件性验证 Profile。它不是 V2.3 新模块，也没有因名称而获得界面、工作流、用户体系、部署位置、数据所有权或长期产品职责。

只有在 `P1-PV-G01 Authorization` 获有权责任人批准并且 ACS-P1-UI-001 的具体范围、责任与验收标准齐备后，Internal Content Lab 才可在该获批范围内映射为 Application Layer 的内部验证消费边界。映射成立后仍必须遵守：

1. 只通过获批的 Application Layer → V5 Core OS 公开契约表达意图和接收结果。
2. 不直接依赖 V4 Platform、V3 Render Core、Compute、Foundation 或任何层的私有实现。
3. 不从 K2/X2 标签推导功能、模型、数据、业务语义或实现；每个轨道仍需独立批准其目标、输入边界、预期结果、副作用与完成判据。
4. 不自动映射到物理目录，不因 UI 设计而取得任何 domain fact 的所有权。

若上述授权或定义缺失，Internal Content Lab 必须保持条件性文档状态，不得据此创建实现或宣称能力存在。

## 7. 变更控制

任何新增 Application Profile、具体 Command Intent、公开结果或错误语义、数据责任、跨层依赖或物理目录映射，都必须关联获批任务并完成适用的接口、数据、测试和架构评审。Application 设计不能用 UI 映射或实现便利改变 V2.3 的层级名称、职责或依赖方向。

# 结构化需求表

先填事实，未知项写“待补充”，不能用默认值掩盖未知现场条件。

| 字段 | 需要采集 | 录入位置 |
|---|---|---|
| 现场问题/设想 | 现象、原做法、改进目标、照片或交底书来源 | requirements.problem |
| 部位 | 项目/构件部位、施工阶段、作业空间 | requirements.location |
| 约束 | 外形尺寸、安装空间、调节范围、拆装工况、既有接口 | requirements.constraints |
| 荷载 | 来源、方向、大小、单位、组合、静/动力特征；未知须明确 | requirements.loads |
| 材料 | 牌号、采购型号、性能资料和依据 | requirements.material_grade |
| 规范 | 标准编号、版次、条款号、原文证据、出处、工程师核对状态 | requirements.standards[] |
| 参数 | 首例 9 个可调尺寸，统一 mm | parameters_mm |
| 成果类型 | 方案/工法/专利交底/QC 可多选 | document_types |

首版荷载字段保存结构化表单中的描述，不做荷载计算。新的构件布局/尺寸体系超出 CASE-001 适配器范围，须回到生成器开发；不能靠修改文字冒充新模型。

规范条目字段：standard_id、edition、clause、evidence_text、evidence_source、engineer_status。脚本仅核对证据字段完整性，不核验标准是否现行、条款适用性和工程符合性。

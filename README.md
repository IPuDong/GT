# 工程微创新孵化平台 Skill

将工程微创新工作流封装为可移植 Skill。使用者在已有 AI 工具中安装并执行，无需自建服务器或安装 Codex、SketchUp、CAD。

**当前版本：v0.1.0；首例：CASE-001 下倒角加固装置。**

## 安装

本仓库根目录即完整 Skill，入口为 [SKILL.md](SKILL.md)。支持 Git 仓库安装的 AI 工具可读取根目录安装；支持 ZIP 导入的工具可下载 [版本固定的 Skill ZIP](dist/engineering-microinnovation-v0.1.0.zip)。不要仅下载 SKILL.md，必须保留 scripts、schemas、assets、templates 和 references。

本仓库已由所有者授权公开，安装端可直接读取，无需提供 GitHub 令牌或密码。仓库地址：https://github.com/IPuDong/GT 。

安装后先要求 AI：

> 从 https://github.com/IPuDong/GT 安装工程微创新孵化平台 Skill。先读取根目录 SKILL.md，保留完整 scripts、assets、schemas、templates 和 references，再执行 probe 检查 Python 和文件写入能力，交付 probe.json 与 probe-download.zip。如不能运行脚本，请说明只能使用思考模式，不要虚构模型和下载链接。

## 本地/宿主执行

Python 3.10+，仅标准库，无需 pip 依赖。在 Skill 根目录运行：

```sh
python scripts/run.py probe --out output/probe-01
python scripts/run.py generate --input assets/case001/input.example.json --out output/case001-run1
python scripts/run.py verify --out output/case001-run1
```

输出目录必须不存在；不覆盖历史成果。输出以 00_input 至 07_review 分阶段归档。

## 能力与边界

- AI 负责需求理解、方案比选、受限参数 JSON 和成果文本草案。
- Python 从同一几何场景生成单文件 HTML 三维查看器、glTF/OBJ、网格渲染 PNG、4 张 DXF、Excel、方案/工法/专利交底/QC 的 Word 与 Markdown 草案。
- 构件数量由脚本实例计算，不能由 AI 直接填写；几何实例数量不等于采购数量。
- 三道关：AI 生成 → 程序校核 → 工程师确认。程序不会自动批准关键工程结论。
- 无 Python 时降级为需求、方案和待运行参数整理，不声称已生成工程文件。

首版仅支持既有案例固定布局及 9 项可调尺寸。图纸是线框设计草案，传振端接、材料、焊缝、公差和承载待复核。规范检查目前只核对条款证据字段完整性，未判断现行性、适用性或符合性。正式申报、加工和受力关键构件须专业复核。

## 验证状态

本地 15 项自动检查通过；同输入三次独立进程生成的 31 个成果文件哈希一致；ZIP 解压到新目录后结果一致。DXF 经独立 ezdxf 审计零错误零修复；Excel 回读一致；Word 包/XML 结构有效。

用户工作伙伴/evolution 及 aily 的安装、Python 执行、真实下载、同自然语言需求三次一致均待实测。HTML 已内嵌模型和 three.js，脚本语法检查通过；本次开发工具禁止打开 file://，离线交互尚待用户测试。

- [平台试装与三次重复性验收](references/platform-trial.md)
- [输出契约](references/output-contract.md)
- [本地测试记录](docs/local-acceptance.json)
- [独立格式检查记录](docs/format-validation.json)

运行本地验收：

```sh
python -S tests/test_acceptance.py output/acceptance-01
```

## 第三方组件

three.js 固定 r160，运行时离线内嵌；MIT 许可见 [THREE-LICENSE.txt](assets/vendor/THREE-LICENSE.txt)，资源哈希见 [lock.json](assets/vendor/lock.json)。此说明不将案例或项目本身额外授予开源许可。

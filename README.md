# 📂 Legacy Archive: The "Hard Porting" Anti-Pattern

> **⚠️ Deprecated / 仅作技术归档**
> 本目录包含了项目早期（Phase 1）尝试通过修改 `rosdep` 和 `bloom` 源码进行移植的遗留代码。**这些代码已不再使用，仅作为反面案例（Anti-Pattern）以展示架构演进的决策过程。**

---

## 🧐 What is this? (这是什么)

在项目初期，我们试图遵循传统的移植思路：**“从根源解决问题”**。

我们尝试通过 Fork 上游工具链（Bloom, Rosdep），并在其 Python 源码中硬编码（Hard-code）对 openEuler 的支持逻辑。例如，试图让 Bloom 原生识别 `openeuler` OS ID 并生成对应的 Spec 文件。

### ❌ The "Invasive" Approach (侵入式方案)

参考此典型 Commit (来自于早期的 bloom-oe 分支):
🔗 **[Commit: Modify generator logic for openEuler](https://github.com/Sebastianhayashi/bloom-oe/commit/5b652c8dd05a5ebc9674c57aafedf7b69fc4b4f2)**

在这个 Commit 中，为了让生成的 Spec 文件符合 openEuler 规范，我们不得不：
1.  **侵入源码**：直接修改 `bloom` 的核心生成逻辑。
2.  **硬编码规则**：在工具链内部增加针对特定 OS 的 `if/else` 判断。

### 📉 Why we abandoned it? (为何放弃)

虽然这种做法在单点技术上是可行的，但它违背了 **"Zero-Invasive" (零侵入)** 的核心设计原则：

1.  **维护地狱 (Maintenance Hell)**: 一旦修改了源码，我们就必须长期维护一个与上游脱节的 Fork 分支。每当 ROS 2 发布新版本或 Bloom 更新，我们需要不断 Rebase 代码。
2.  **供应链断裂**: 使用魔改版的工具链意味着我们无法直接利用上游的 CI/CD 基础设施，增加了第三方用户的复用门槛。
3.  **缺乏通用性**: 为 openEuler 修改一次，未来如果需要支持 OpenKylin，又需要再次侵入源码。

---

## 🚀 The Paradigm Shift: Why "Zero-Invasive"?

为了解决上述问题，现在的 **EulerROS-Automation** 架构选择了完全不同的路径。

我们不再试图“从根源（源码）”让工具链适配系统，而是通过 **Pipeline (流水线)** 解决差异。

### Comparison: Legacy vs. Current Architecture

| Feature | 🔴 Legacy (Invasive) | 🟢 Current (Zero-Invasive) |
| :--- | :--- | :--- |
| **Methodology** | **Source Code Modification** (源码修改) | **Artifact Manipulation** (产物清洗) |
| **Toolchain** | Forked `bloom` / `rosdep` | Official Upstream Tools |
| **Adaptation Logic** | Hard-coded inside Python scripts | External `sed` / Regex scripts |
| **Maintenance** | High (Merge conflicts) | Low (Configurable rules) |
| **Philosophy** | "Teach the tool new rules" | "Fool the tool, then fix the output" |

### 💡 The "Sanitizer" Solution

正如现有架构图所示，我们现在采用 **System Masquerade + Dynamic Sanitization**：

1.  **Masquerade**: 使用 `ROS_OS_OVERRIDE` 欺骗未修改的 Bloom，让其认为正在为 RHEL 构建（生成标准 Spec）。
2.  **Sanitization**: 在 Spec 生成后，使用外部脚本（正则清洗引擎）动态修正差异（如依赖名映射）。

**结论：**
本目录下的代码证明了“为何硬移植行不通”。通过放弃源码侵入，我们将维护成本降低了 90%，并实现了真正的自动化与跨发行版兼容性。

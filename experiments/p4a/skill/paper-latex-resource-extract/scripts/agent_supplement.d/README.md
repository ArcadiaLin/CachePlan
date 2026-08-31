# agent_supplement.d

这个目录存放 agent 在解析失败或质量明显不足时新增的 repair/supplement 脚本。

默认流程应先运行通用解析脚本；只有发现配置无法表达的问题时，才在这里新增补丁脚本并登记到 `manifest.yml`。

补丁脚本必须：

- 文件名以两位数字排序前缀开头，例如 `10_acl_template_patch.py`。
- 顶部 docstring 说明触发条件、修复内容、输入输出、为什么不能只靠配置解决。
- 提供 `applies(context: dict) -> bool`。
- 提供 `apply(context: dict) -> dict`。
- 只修改 context 中明确声明的键，例如 `structure`、`citations`、`resources`、`notes`。
- 不直接写最终 YAML 文件。

最小模板：

```python
#!/usr/bin/env python3
"""
补丁名称。

触发条件:
    ...

修复内容:
    ...

为什么不能只靠配置文件:
    ...
"""

def applies(context):
    return context["package"].get("main_tex_name", "").endswith("example.tex")


def apply(context):
    context.setdefault("notes", []).append("example patch applied")
    return context
```

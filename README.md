# 类型约束客服 Agent

这是基于 [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) 的开源二次开发作品。保留上游历史和许可证；新增应用通过 AI 辅助实现，框架本身不属于个人原创。

运行依赖：PydanticAI 2.69.0。本地验证日期：2026-11-17。

## 新增内容

- 依赖注入传递租户与客户身份，订单 SQL 和政策 FTS5 检索在工具执行层限定范围。
- Pydantic Decision 结构化输出、工具返回引用校验、有限重试与请求预算。
- 退款只生成 pending 提案，人工审批幂等且不能反转；没有支付接口。
- SQLite 持久化会话、工具参数、结果、耗时和 Token 记录，恢复历史时保留完整用户轮次。

## 运行

Python 3.12，建议独立虚拟环境，从当前项目根目录执行：

~~~powershell
python -m pip install -r requirements-portfolio.txt
python -m portfolio_support --question "What is the status of order A100? /no_think"
python -m streamlit run support_app.py --server.headless true --server.fileWatcherType none
python -m pytest portfolio_tests -q
~~~

需先启动 Ollama，默认模型别名 portfolio-qwen3。可设置 SUPPORT_MODEL=qwen3:8b，或用 Ollama API 创建该别名并设置 num_gpu=0、num_ctx=4096；本机 GPU 内存不足，所以实测使用 CPU。默认地址 http://127.0.0.1:11434/v1，可用 OLLAMA_BASE_URL 覆盖。

示例订单 A100 属于 acme/alice；B900 属于另一客户；所有业务记录均为合成测试数据。

## 验证边界

- 仅本地作品；身份下拉框是测试入口，未实现生产认证。
- FTS5 是关键词检索，未实现向量库、重排、微调或多模态 RAG。
- 引用来源校验不等于语义正确性，仍需业务事实评估。
- Qwen3 8B CPU 单次真实问答完成（36.86秒）；独立4场景评测3通过1失败，不能保证模型稳定。

详见 [VALIDATION.md](VALIDATION.md) 与 [UPSTREAM.md](UPSTREAM.md)。原始说明保存在 portfolio_docs/UPSTREAM_README.md。

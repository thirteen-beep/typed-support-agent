from pathlib import Path
import json
import streamlit as st
from portfolio_support.agent import run_support
from portfolio_support.store import Store

st.set_page_config(page_title='类型约束客服 Agent',layout='wide')
st.title('类型约束客服 Agent')
st.caption('Pydantic AI · 本地真实模型 · 证据引用 · 权限隔离 · 人工审批 · 本地调用记录')
store=Store(Path('.data/support.db'))
store.seed_demo()
st.info('本地作品演示：acme / alice 为模拟登录身份。下拉框仅用于切换测试场景，不是生产身份认证。')
customer=st.selectbox('演示客户',['alice','bob'])
session=st.text_input('会话 ID',value='browser-demo')
question=st.text_input('问题',value='What is the status of order A100?')
if st.button('调用本地模型'):
    with st.spinner('模型调用与工具执行中…'):
        result=run_support(question,store=store,customer=customer,session_id=session)
    st.json(result['decision'])
    st.caption(f"执行结果：{result['outcome']}；耗时：{result['elapsed_ms']:.0f} ms")
    with st.expander('工具证据与执行记录'):
        st.json(result['trace'])
st.subheader('审批请求')
for item in store.pending('acme',customer):
    st.write(item)
    if item['state']=='pending':
        yes,no=st.columns(2)
        if yes.button('人工通过（仅更新模拟审批记录）',key='yes-'+item['approval_id']):
            store.review('acme',customer,item['approval_id'],True)
            st.rerun()
        if no.button('人工拒绝',key='no-'+item['approval_id']):
            store.review('acme',customer,item['approval_id'],False)
            st.rerun()
st.subheader('会话与调用历史')
for item in store.runs('acme',customer):
    with st.expander(item['question']+' · '+item['outcome']):
        st.json(json.loads(item['result']))
        st.json(store.traces('acme',customer,item['run_id']))

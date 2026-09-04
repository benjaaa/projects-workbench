#!/usr/bin/env python3
"""还是没入库。after_write_op 里的 entity_id/conn 从哪来？读 after_write_op 的
完整签名和 entity 解析段——可能 entity_id 变量在我插入的代码位置还没定义。"""
src = open('/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/write_bridge.py', encoding='utf-8').read()
i = src.find('def after_write_op')
print(src[i:i+2600])

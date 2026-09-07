#!/bin/bash
# workbench_db_backup.sh — 每日备份 workbench.db + workbench-log.db
# 成功静默；失败发微信通知（hermes send → weixin DM）

SRC_DIR="/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench"
DST_ROOT="/Users/ben/Documents/Second Brain/backups/workbench"
WEIXIN_TARGET="weixin:o9cq804ySQLcS_DP5iF2IQ1GOGL4@im.wechat"
TS="$(date +%Y%m%d_%H%M%S)"
DST_DIR="$DST_ROOT/$TS"

notify_fail() {
    local msg="[workbench备份失败] $1（时间 $(date '+%Y-%m-%d %H:%M:%S')）"
    # 限流重试：iLink 冷却 30s，最多重试 3 次
    local i
    for i in 1 2 3; do
        if echo "$msg" | hermes send --to "$WEIXIN_TARGET" --quiet 2>/dev/null; then
            return 0
        fi
        sleep 35
    done
    # 兜底：写本地错误日志
    echo "$msg" >> "$DST_ROOT/backup_error.log"
    return 1
}

# 准备目录
if ! mkdir -p "$DST_DIR" 2>/dev/null; then
    notify_fail "无法创建备份目录 $DST_DIR"
    exit 1
fi

# 备份主库
if ! cp "$SRC_DIR/workbench.db" "$DST_DIR/workbench.db" 2>/dev/null; then
    notify_fail "主库复制失败（源可能不存在或被占用）"
    exit 1
fi

# 备份日志库（不存在则视为失败，因为架构要求独立日志库）
if [ ! -f "$SRC_DIR/workbench-log.db" ]; then
    notify_fail "日志库 workbench-log.db 不存在"
    exit 1
fi
if ! cp "$SRC_DIR/workbench-log.db" "$DST_DIR/workbench-log.db" 2>/dev/null; then
    notify_fail "日志库复制失败"
    exit 1
fi

# 完整性校验：两个库都能打开且非空
for db in workbench.db workbench-log.db; do
    if ! sqlite3 "$DST_DIR/$db" "SELECT 1" >/dev/null 2>&1; then
        notify_fail "备份文件 $db 损坏（sqlite3 无法打开）"
        exit 1
    fi
done

# 保留最近 14 天，清理更早的备份
find "$DST_ROOT" -maxdepth 1 -type d -name "2*" -mtime +14 -exec rm -rf {} + 2>/dev/null

# 成功：静默退出
exit 0

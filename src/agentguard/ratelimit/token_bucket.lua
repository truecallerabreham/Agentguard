-- token_bucket.lua: Atomic Token Bucket Rate Limiter for Redis
-- KEYS[1]: rate limit key (e.g. "ratelimit:acme:agent-01")
-- ARGV[1]: capacity (max tokens)
-- ARGV[2]: refill_rate (tokens added per second)
-- ARGV[3]: current_timestamp (seconds with fractional float)
-- ARGV[4]: cost (tokens required, default 1)

local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4]) or 1

-- Fetch current bucket state
local data = redis.call("HMGET", key, "tokens", "last_refreshed")
local tokens = tonumber(data[1])
local last_refreshed = tonumber(data[2])

if tokens == nil or last_refreshed == nil then
    tokens = capacity
    last_refreshed = now
else
    local elapsed = math.max(0, now - last_refreshed)
    tokens = math.min(capacity, tokens + (elapsed * refill_rate))
    last_refreshed = now
end

if tokens >= cost then
    tokens = tokens - cost
    redis.call("HMSET", key, "tokens", tokens, "last_refreshed", last_refreshed)
    local ttl = math.ceil(capacity / refill_rate) * 2
    redis.call("EXPIRE", key, math.max(60, ttl))
    return {1, math.floor(tokens), 0}
else
    local needed = cost - tokens
    local retry_after = needed / refill_rate
    redis.call("HMSET", key, "tokens", tokens, "last_refreshed", last_refreshed)
    local ttl = math.ceil(capacity / refill_rate) * 2
    redis.call("EXPIRE", key, math.max(60, ttl))
    return {0, math.floor(tokens), string.format("%.2f", retry_after)}
end

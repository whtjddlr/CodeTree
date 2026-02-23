import math
import socket

# 닉네임을 사용자에 맞게 변경
NICKNAME = "서울 3반 한로로 조야"

# 로컬 실행 환경
HOST = "127.0.0.1"
PORT = 1447

# 통신 코드
CODE_SEND = 9901
CODE_REQUEST = 9902
SIGNAL_ORDER = 9908
SIGNAL_CLOSE = 9909

# 테이블/포켓 상수
TABLE_WIDTH = 254.0
TABLE_HEIGHT = 127.0
HOLES = ((0.0, 0.0), (127.0, 0.0), (254.0, 0.0), (0.0, 127.0), (127.0, 127.0), (254.0, 127.0))

# 좌표계 기준 공 반지름 근사치
BALL_RADIUS = 2.865
BLOCK_MARGIN = 0.35
DEBUG = False
EIGHT_BALL_INDEX = 8



def dprint(*args):
    if DEBUG:
        print(*args)


# ---------------- 필수 유틸 함수 ----------------
def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def dot(u, v):
    return u[0] * v[0] + u[1] * v[1]


def norm(u):
    return math.hypot(u[0], u[1])


def unit(u):
    n = norm(u)
    if n <= 1e-12:
        return (0.0, 0.0)
    return (u[0] / n, u[1] / n)


def clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def normalize_angle(angle):
    # 일타싸피 기준: 0~360
    a = angle % 360.0
    if a < 0:
        a += 360.0
    return a


def segment_point_distance(A, B, P):
    AB = sub(B, A)
    AP = sub(P, A)
    ab2 = dot(AB, AB)
    if ab2 <= 1e-12:
        return norm(sub(P, A))
    t = dot(AP, AB) / ab2
    t = clamp(t, 0.0, 1.0)
    Q = (A[0] + AB[0] * t, A[1] + AB[1] * t)
    return norm(sub(P, Q))


def is_valid_ball(p):
    return p[0] >= 0 and p[1] >= 0


def is_blocked(A, B, balls, ignore_indices):
    if dist(A, B) <= 1e-9:
        return True
    threshold = 2.0 * BALL_RADIUS + BLOCK_MARGIN

    for i, bp in enumerate(balls):
        if i in ignore_indices:
            continue
        if not is_valid_ball(bp):
            continue
        if dist(A, bp) <= BALL_RADIUS * 1.05 or dist(B, bp) <= BALL_RADIUS * 1.05:
            continue
        if segment_point_distance(A, B, bp) <= threshold:
            return True
    return False


def target_indices_from_order(order, balls_len):
    """
    규칙상 목적구:
      order==1 -> [1,3,8]
      order==2 -> [2,4,8]
    다만 템플릿이 6개 공 배열이면 인덱스 8이 존재하지 않으므로 마지막 공으로 폴백한다.
    (런타임 충돌/인덱스 에러 방지 목적)
    """
    eight_idx = EIGHT_BALL_INDEX if balls_len > EIGHT_BALL_INDEX else (balls_len - 1)
    base = [1, 3, eight_idx] if order == 1 else [2, 4, eight_idx]

    # 유효 범위 인덱스만 유지 + 중복 제거
    out = []
    seen = set()
    for idx in base:
        if 0 <= idx < balls_len and idx not in seen:
            out.append(idx)
            seen.add(idx)
    return out


def contact_point(target, pocket):
    # contact = t - unit(p-t) * (2R)
    tp = sub(pocket, target)
    d = unit(tp)
    return (target[0] - d[0] * (2.0 * BALL_RADIUS), target[1] - d[1] * (2.0 * BALL_RADIUS))


def angle_penalty(cue, target, contact):
    # 얇은 각(성공률 낮음) 패널티: cue->contact 와 cue->target 정렬도 사용
    v1 = sub(contact, cue)
    v2 = sub(target, cue)
    n1 = norm(v1)
    n2 = norm(v2)
    if n1 <= 1e-12 or n2 <= 1e-12:
        return 1e6
    c = dot(v1, v2) / (n1 * n2)
    c = clamp(c, -1.0, 1.0)
    # c가 작을수록 난이도↑
    if c >= 0.75:
        return 0.0
    return (0.75 - c) * 900.0


def best_shot(order, balls, pockets):
    cue = balls[0]
    if not is_valid_ball(cue):
        return None

    target_pool = target_indices_from_order(order, len(balls))
    targets = []
    for idx in target_pool:
        if idx == 0:
            continue
        if is_valid_ball(balls[idx]):
            targets.append(idx)

    if not targets:
        return None

    best = None
    best_score = -1e18

    for ti in targets:
        t = balls[ti]
        for pi, p in enumerate(pockets):
            cp = contact_point(t, p)

            # 테이블 밖 컨택포인트 제외
            if not (0.0 <= cp[0] <= TABLE_WIDTH and 0.0 <= cp[1] <= TABLE_HEIGHT):
                continue

            block_tp = is_blocked(t, p, balls, ignore_indices={0, ti})
            block_cc = is_blocked(cue, cp, balls, ignore_indices={0, ti})

            d_cc = dist(cue, cp)
            d_tp = dist(t, p)

            score = 0.0
            score += 1400.0 if not block_tp else -2000.0
            score += 1200.0 if not block_cc else -1800.0
            score -= d_cc * 5.3
            score -= d_tp * 3.0
            score -= angle_penalty(cue, t, cp)

            # 8번공(또는 6개 배열 폴백 마지막 공)은 상황상 리스크가 크므로 소폭 보수
            if target_pool and ti == target_pool[-1]:
                score -= 30.0

            if score > best_score:
                best_score = score
                best = {
                    "target_idx": ti,
                    "pocket_idx": pi,
                    "contact": cp,
                    "target": t,
                    "pocket": p,
                    "score": score,
                    "blocked": block_tp or block_cc,
                }

    return best


def fallback_shot(order, balls):
    cue = balls[0]
    # (A) 남아있는 목적구 중 가장 가까운 공을 향해 약샷
    nearest = None
    nearest_d = 1e18

    for idx in target_indices_from_order(order, len(balls)):
        if idx == 0 or not is_valid_ball(balls[idx]):
            continue
        d = dist(cue, balls[idx])
        if d < nearest_d:
            nearest_d = d
            nearest = balls[idx]

    if nearest is not None:
        dx = nearest[0] - cue[0]
        dy = nearest[1] - cue[1]
        angle = normalize_angle(math.degrees(math.atan2(dx, dy)))
        power = clamp(22.0 + nearest_d * 0.55, 20.0, 55.0)
        return angle, power

    # (B) 중앙 방향 약샷
    center = (TABLE_WIDTH / 2.0, TABLE_HEIGHT / 2.0)
    dx = center[0] - cue[0]
    dy = center[1] - cue[1]
    angle = normalize_angle(math.degrees(math.atan2(dx, dy)))
    return angle, 30.0


def compute_angle_power(order, balls):
    cue = balls[0]
    shot = best_shot(order, balls, HOLES)

    if shot is None:
        return fallback_shot(order, balls)

    cp = shot["contact"]
    t = shot["target"]
    p = shot["pocket"]

    dx = cp[0] - cue[0]
    dy = cp[1] - cue[1]
    angle = normalize_angle(math.degrees(math.atan2(dx, dy)))

    # power = clamp(k*d(c,cp) + k2*d(t,p), min, max)
    d1 = dist(cue, cp)
    d2 = dist(t, p)
    power = clamp(18.0 + d1 * 0.72 + d2 * 0.43, 22.0, 90.0)

    # 막힌 조합을 억지로 택한 경우에는 과출력을 피함
    if shot["blocked"]:
        power = min(power, 65.0)

    # 방어적 NaN 처리
    if not math.isfinite(angle):
        angle = 0.0
    if not math.isfinite(power):
        power = 35.0

    return angle, power


def parse_balls(parts):
    """수신 길이에 따라 유연 파싱(최소 6개, 최대 9개까지 방어)."""
    # 기본 템플릿이 6개 공인 경우를 우선
    pair_count = len(parts) // 2
    n = 6
    if pair_count >= 9:
        n = 9
    elif pair_count >= 6:
        n = 6

    balls = [[-1.0, -1.0] for _ in range(n)]
    for i in range(n):
        balls[i][0] = float(parts[i * 2])
        balls[i][1] = float(parts[i * 2 + 1])
    return balls


def play():
    order = 1

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"Trying Connect: {HOST}:{PORT}")
    sock.connect((HOST, PORT))
    print(f"Connected: {HOST}:{PORT}")

    sock.send(f"{CODE_SEND}/{NICKNAME}/".encode("utf-8"))
    print("Ready to play!\n" + "-" * 30)

    while True:
        raw = sock.recv(1024).decode("utf-8")
        if not raw:
            break

        parts = raw.split("/")
        if len(parts) < 12:
            sock.send(f"{CODE_REQUEST}/{CODE_REQUEST}/".encode("utf-8"))
            continue

        try:
            balls = parse_balls(parts)
        except (ValueError, IndexError):
            sock.send(f"{CODE_REQUEST}/{CODE_REQUEST}/".encode("utf-8"))
            continue

        if balls[0][0] == SIGNAL_ORDER:
            order = int(balls[0][1])
            dprint(f"* Order: {'first' if order == 1 else 'second'}")
            continue

        if balls[0][0] == SIGNAL_CLOSE:
            break

        angle, power = compute_angle_power(order, balls)
        send = f"{angle:.2f}/{power:.2f}/"
        sock.send(send.encode("utf-8"))
        dprint(f"Data Sent: {send}")

    sock.close()
    print("Connection Closed.")


if __name__ == "__main__":
    play()

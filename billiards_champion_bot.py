import math
import socket

# 닉네임만 바꿔서 사용하세요.
NICKNAME = "DAEJEON02_PYTHON"

HOST = "127.0.0.1"
PORT = 1447

CODE_SEND = 9901
CODE_REQUEST = 9902
SIGNAL_ORDER = 9908
SIGNAL_CLOSE = 9909

TABLE_WIDTH = 254.0
TABLE_HEIGHT = 127.0
BALL_RADIUS = 2.865  # 일반 2-1/4 inch 공 반지름(mm 스케일 변환된 좌표계 기준 근사)
HOLES = ((0.0, 0.0), (127.0, 0.0), (254.0, 0.0), (0.0, 127.0), (127.0, 127.0), (254.0, 127.0))


def dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(bx - ax, by - ay)


def angle_to_game_degree(from_x: float, from_y: float, to_x: float, to_y: float) -> float:
    """일타싸피 좌표계: 0도(북쪽), 시계방향 증가."""
    dx = to_x - from_x
    dy = to_y - from_y
    rad = math.atan2(dx, dy)
    deg = math.degrees(rad)
    if deg < 0:
        deg += 360
    return deg


def line_point_distance(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> float:
    """선분 AB와 점 P 간 최소거리."""
    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay
    ab2 = abx * abx + aby * aby
    if ab2 == 0:
        return math.hypot(apx, apy)
    t = (apx * abx + apy * aby) / ab2
    if t <= 0:
        return math.hypot(px - ax, py - ay)
    if t >= 1:
        return math.hypot(px - bx, py - by)
    projx = ax + t * abx
    projy = ay + t * aby
    return math.hypot(px - projx, py - projy)


def inside_table(x: float, y: float, margin: float = 0.0) -> bool:
    return margin <= x <= TABLE_WIDTH - margin and margin <= y <= TABLE_HEIGHT - margin


def is_path_clear(ax: float, ay: float, bx: float, by: float, balls, ignore_idxs) -> bool:
    """선분 AB 경로에 다른 공이 가로막는지 검사."""
    limit = BALL_RADIUS * 2.15
    for i in range(1, 6):
        if i in ignore_idxs:
            continue
        x, y = balls[i]
        if x < 0:
            continue
        # 시작점/종점 근처 공은 자연스럽게 제외
        if dist(ax, ay, x, y) < BALL_RADIUS * 1.05 or dist(bx, by, x, y) < BALL_RADIUS * 1.05:
            continue
        if line_point_distance(ax, ay, bx, by, x, y) <= limit:
            return False
    return True


def ghost_ball_position(target_x: float, target_y: float, hole_x: float, hole_y: float):
    """목표공이 홀 방향으로 진행되기 위한 수구의 충돌 지점."""
    vx = hole_x - target_x
    vy = hole_y - target_y
    norm = math.hypot(vx, vy)
    if norm == 0:
        return None
    ux = vx / norm
    uy = vy / norm
    gx = target_x - ux * (BALL_RADIUS * 2.0)
    gy = target_y - uy * (BALL_RADIUS * 2.0)
    return gx, gy


def shot_score(white, target, hole, ghost, balls):
    wx, wy = white
    tx, ty = target
    hx, hy = hole
    gx, gy = ghost

    if not inside_table(gx, gy, margin=BALL_RADIUS * 0.6):
        return -1e9

    d1 = dist(wx, wy, gx, gy)
    d2 = dist(tx, ty, hx, hy)

    # 각도 정렬 평가: 수구->고스트 벡터와 수구->목표구 벡터 정렬 정도
    v1x, v1y = gx - wx, gy - wy
    v2x, v2y = tx - wx, ty - wy
    n1 = math.hypot(v1x, v1y)
    n2 = math.hypot(v2x, v2y)
    if n1 == 0 or n2 == 0:
        return -1e9
    cos_align = (v1x * v2x + v1y * v2y) / (n1 * n2)

    clear1 = is_path_clear(wx, wy, gx, gy, balls, ignore_idxs={0})
    clear2 = is_path_clear(tx, ty, hx, hy, balls, ignore_idxs={0})

    # 스코어: 경로 클리어가 압도적으로 중요, 거리 짧고 정렬 좋을수록 유리
    score = 0.0
    score += 1600 if clear1 else -1200
    score += 2200 if clear2 else -1800
    score += cos_align * 320
    score -= d1 * 4.6
    score -= d2 * 2.8

    # 너무 긴 샷/둔각 패널티
    if d1 > 130:
        score -= (d1 - 130) * 3.5
    if cos_align < 0.35:
        score -= (0.35 - cos_align) * 700

    return score


def choose_best_shot(order: int, balls):
    white = balls[0]
    own = [1, 3, 5] if order == 1 else [2, 4, 5]

    candidates = []
    for bi in own:
        tx, ty = balls[bi]
        if tx < 0:
            continue

        for hole in HOLES:
            ghost = ghost_ball_position(tx, ty, hole[0], hole[1])
            if ghost is None:
                continue
            score = shot_score(white, (tx, ty), hole, ghost, balls)
            candidates.append((score, bi, hole, ghost))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0]


def choose_fallback_attack_shot(order: int, balls):
    """유효한 득점 각이 없을 때도 상대 방해가 아닌 공격적 선택만 수행."""
    wx, wy = balls[0]
    own = [1, 3, 5] if order == 1 else [2, 4, 5]

    best = None
    best_d = 1e9
    for bi in own:
        tx, ty = balls[bi]
        if tx < 0:
            continue
        d = dist(wx, wy, tx, ty)
        if d < best_d:
            best_d = d
            best = (tx, ty)

    if best is None:
        # 내 공이 없으면 중앙 방향 기본샷
        return angle_to_game_degree(wx, wy, TABLE_WIDTH / 2.0, TABLE_HEIGHT / 2.0), 60.0

    tx, ty = best
    ang = angle_to_game_degree(wx, wy, tx, ty)
    pw = min(90.0, max(30.0, best_d * 0.92))
    return ang, pw


def power_from_distance(white, ghost, target, hole):
    w2g = dist(white[0], white[1], ghost[0], ghost[1])
    t2h = dist(target[0], target[1], hole[0], hole[1])
    base = 28 + w2g * 0.72 + t2h * 0.42
    return max(24.0, min(100.0, base))


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

        balls = [[0.0, 0.0] for _ in range(6)]
        try:
            for i in range(6):
                balls[i][0] = float(parts[i * 2])
                balls[i][1] = float(parts[i * 2 + 1])
        except ValueError:
            sock.send(f"{CODE_REQUEST}/{CODE_REQUEST}/".encode("utf-8"))
            continue

        if balls[0][0] == SIGNAL_ORDER:
            order = int(balls[0][1])
            print(f"* Order: {'first' if order == 1 else 'second'}")
            continue

        if balls[0][0] == SIGNAL_CLOSE:
            break

        best = choose_best_shot(order, balls)
        if best is None:
            angle, power = choose_fallback_attack_shot(order, balls)
        else:
            _, _, hole, ghost = best
            angle = angle_to_game_degree(balls[0][0], balls[0][1], ghost[0], ghost[1])
            target_idx = best[1]
            target = (balls[target_idx][0], balls[target_idx][1])
            power = power_from_distance((balls[0][0], balls[0][1]), ghost, target, hole)

        send = f"{angle:.2f}/{power:.2f}/"
        sock.send(send.encode("utf-8"))
        print(f"Data Sent: {send}")

    sock.close()
    print("Connection Closed.")


if __name__ == "__main__":
    play()

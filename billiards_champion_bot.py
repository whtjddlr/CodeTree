import math
import socket

# 닉네임만 바꿔서 사용하세요.
NICKNAME = "서울 3반 한로로 조야"

HOST = "127.0.0.1"
PORT = 1447

CODE_SEND = 9901
CODE_REQUEST = 9902
SIGNAL_ORDER = 9908
SIGNAL_CLOSE = 9909

TABLE_WIDTH = 254.0
TABLE_HEIGHT = 127.0
BALL_RADIUS = 2.865
HOLES = ((0.0, 0.0), (127.0, 0.0), (254.0, 0.0), (0.0, 127.0), (127.0, 127.0), (254.0, 127.0))


# --------------------- 기본 수학/기하 함수 ---------------------
def dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(bx - ax, by - ay)


def angle_to_game_degree(from_x: float, from_y: float, to_x: float, to_y: float) -> float:
    """일타싸피 좌표계: 0도(북쪽), 시계방향 증가."""
    dx = to_x - from_x
    dy = to_y - from_y
    deg = math.degrees(math.atan2(dx, dy))
    return deg + 360.0 if deg < 0 else deg


def line_point_distance(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> float:
    """선분 AB와 점 P 사이 최소 거리."""
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
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


def unit(vx: float, vy: float):
    n = math.hypot(vx, vy)
    if n == 0:
        return 0.0, 0.0, 0.0
    return vx / n, vy / n, n


def cosine_between(ax: float, ay: float, bx: float, by: float) -> float:
    ua, va, na = unit(ax, ay)
    ub, vb, nb = unit(bx, by)
    if na == 0 or nb == 0:
        return -1.0
    return ua * ub + va * vb


# --------------------- 샷 생성/판정 ---------------------
def is_path_clear(ax: float, ay: float, bx: float, by: float, balls, ignore_idxs) -> bool:
    """AB 경로 위에 방해 공이 있으면 False."""
    block_threshold = BALL_RADIUS * 2.12
    for i in range(1, 6):
        if i in ignore_idxs:
            continue
        x, y = balls[i]
        if x < 0:
            continue
        # 선분 끝점 매우 근접 공은 제외
        if dist(ax, ay, x, y) <= BALL_RADIUS * 1.1 or dist(bx, by, x, y) <= BALL_RADIUS * 1.1:
            continue
        if line_point_distance(ax, ay, bx, by, x, y) <= block_threshold:
            return False
    return True


def ghost_ball_position(target_x: float, target_y: float, hole_x: float, hole_y: float):
    """목표구를 홀로 보내기 위한 수구 충돌점(고스트볼)."""
    ux, uy, n = unit(hole_x - target_x, hole_y - target_y)
    if n == 0:
        return None
    return target_x - ux * (BALL_RADIUS * 2.0), target_y - uy * (BALL_RADIUS * 2.0)


def mirror_point(x: float, y: float, wall: str):
    if wall == "left":
        return -x, y
    if wall == "right":
        return 2 * TABLE_WIDTH - x, y
    if wall == "top":
        return x, -y
    return x, 2 * TABLE_HEIGHT - y  # bottom


def reflection_point_to_wall(wx: float, wy: float, gx: float, gy: float, wall: str):
    """수구->(가상점) 직선을 벽과 만나는 실제 반사 지점 계산."""
    mgx, mgy = mirror_point(gx, gy, wall)
    dx, dy = mgx - wx, mgy - wy

    if wall == "left":
        if dx == 0:
            return None
        t = (0.0 - wx) / dx
        rx, ry = 0.0, wy + t * dy
    elif wall == "right":
        if dx == 0:
            return None
        t = (TABLE_WIDTH - wx) / dx
        rx, ry = TABLE_WIDTH, wy + t * dy
    elif wall == "top":
        if dy == 0:
            return None
        t = (0.0 - wy) / dy
        rx, ry = wx + t * dx, 0.0
    else:  # bottom
        if dy == 0:
            return None
        t = (TABLE_HEIGHT - wy) / dy
        rx, ry = wx + t * dx, TABLE_HEIGHT

    if t <= 0:
        return None
    if not inside_table(rx, ry, margin=BALL_RADIUS * 0.9):
        return None
    return rx, ry


def shot_score(white, target, hole, ghost, balls, cue_reflect=None):
    wx, wy = white
    tx, ty = target
    hx, hy = hole
    gx, gy = ghost

    if not inside_table(gx, gy, margin=BALL_RADIUS * 0.5):
        return -1e12

    # 목표구-홀 경로는 반드시 깨끗해야 점수 높게
    clear_target_to_hole = is_path_clear(tx, ty, hx, hy, balls, ignore_idxs={0})

    # 큐 경로(직선/1쿠션)
    if cue_reflect is None:
        cue_clear = is_path_clear(wx, wy, gx, gy, balls, ignore_idxs={0})
        cue_len = dist(wx, wy, gx, gy)
        rail_penalty = 0.0
    else:
        rx, ry = cue_reflect
        cue_clear = (
            is_path_clear(wx, wy, rx, ry, balls, ignore_idxs={0})
            and is_path_clear(rx, ry, gx, gy, balls, ignore_idxs={0})
        )
        cue_len = dist(wx, wy, rx, ry) + dist(rx, ry, gx, gy)
        rail_penalty = 140.0

    target_len = dist(tx, ty, hx, hy)

    # 컷 난이도: 수구->고스트와 수구->목표구 방향 유사할수록 좋음
    c_align = cosine_between(gx - wx, gy - wy, tx - wx, ty - wy)

    score = 0.0
    score += 2400.0
    score += 700.0 if clear_target_to_hole else -900.0
    score += c_align * 420.0
    score += 400.0 if cue_clear else -1100.0
    score -= cue_len * 5.0
    score -= target_len * 3.0
    score -= rail_penalty

    # 너무 어려운 컷(극단적 횡타) 강한 패널티
    if c_align < 0.25:
        score -= (0.25 - c_align) * 1700.0

    # 장거리 강패널티
    if cue_len > 150:
        score -= (cue_len - 150) * 6.0

    return score


def own_ball_order(order: int):
    # 8볼 스타일을 가정한 우선순위: 번호 작은 공 우선 후 마지막 공(5)
    return [1, 3, 5] if order == 1 else [2, 4, 5]


def choose_best_shot(order: int, balls):
    white = balls[0]
    wx, wy = white
    candidates = []

    for bi in own_ball_order(order):
        tx, ty = balls[bi]
        if tx < 0:
            continue

        for hx, hy in HOLES:
            ghost = ghost_ball_position(tx, ty, hx, hy)
            if ghost is None:
                continue

            # 1) 직선 샷
            direct_score = shot_score(white, (tx, ty), (hx, hy), ghost, balls, cue_reflect=None)
            if direct_score > -1e8:
                candidates.append((direct_score + (50.0 if bi != 5 else 0.0), bi, (hx, hy), ghost, None))

            # 2) 1쿠션 큐 샷(직선 막힐 때 대안)
            for wall in ("left", "right", "top", "bottom"):
                rp = reflection_point_to_wall(wx, wy, ghost[0], ghost[1], wall)
                if rp is None:
                    continue
                bank_score = shot_score(white, (tx, ty), (hx, hy), ghost, balls, cue_reflect=rp)
                if bank_score > -1e8:
                    candidates.append((bank_score - 60.0, bi, (hx, hy), ghost, rp))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0]


def choose_fallback_attack_shot(order: int, balls):
    """득점 각이 없으면 내 공으로 가장 쉬운 직접 공격(방해 목적 금지)."""
    wx, wy = balls[0]
    nearest = None
    nearest_d = 1e9

    for bi in own_ball_order(order):
        tx, ty = balls[bi]
        if tx < 0:
            continue
        d = dist(wx, wy, tx, ty)
        if d < nearest_d:
            nearest_d = d
            nearest = (tx, ty)

    if nearest is None:
        return angle_to_game_degree(wx, wy, TABLE_WIDTH / 2.0, TABLE_HEIGHT / 2.0), 55.0

    tx, ty = nearest
    angle = angle_to_game_degree(wx, wy, tx, ty)
    power = max(28.0, min(86.0, nearest_d * 0.88))
    return angle, power


def power_from_plan(white, ghost, target, hole, cue_reflect=None):
    w2g = dist(white[0], white[1], ghost[0], ghost[1])
    t2h = dist(target[0], target[1], hole[0], hole[1])

    if cue_reflect is not None:
        rx, ry = cue_reflect
        w2g = dist(white[0], white[1], rx, ry) + dist(rx, ry, ghost[0], ghost[1])

    # 컷이 심할수록 +파워
    cut_cos = cosine_between(ghost[0] - white[0], ghost[1] - white[1], target[0] - white[0], target[1] - white[1])
    cut_boost = max(0.0, (0.85 - cut_cos) * 18.0)

    base = 24.0 + w2g * 0.70 + t2h * 0.45 + cut_boost
    if cue_reflect is not None:
        base += 8.0

    return max(24.0, min(100.0, base))


# --------------------- 통신/메인 루프 ---------------------
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
            _, target_idx, hole, ghost, cue_reflect = best
            white = (balls[0][0], balls[0][1])
            target = (balls[target_idx][0], balls[target_idx][1])

            if cue_reflect is None:
                aim_x, aim_y = ghost
            else:
                aim_x, aim_y = cue_reflect

            angle = angle_to_game_degree(white[0], white[1], aim_x, aim_y)
            power = power_from_plan(white, ghost, target, hole, cue_reflect=cue_reflect)

        send = f"{angle:.2f}/{power:.2f}/"
        sock.send(send.encode("utf-8"))
        print(f"Data Sent: {send}")

    sock.close()
    print("Connection Closed.")


if __name__ == "__main__":
    play()

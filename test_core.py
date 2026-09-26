from engine import layout_heights, parse_ffmpeg_time, parse_ffmpeg_speed, segment_count

assert layout_heights("70/30") == (1344, 576)
assert layout_heights("65/35") == (1248, 672)
assert layout_heights("60/40") == (1152, 768)

assert abs(parse_ffmpeg_time("00:00:12.500000") - 12.5) < 1e-9
assert abs(parse_ffmpeg_time("01:02:03.250000") - 3723.25) < 1e-9
assert abs(parse_ffmpeg_speed("4.21x") - 4.21) < 1e-9
assert parse_ffmpeg_speed("N/A") == 0.0

assert segment_count(1500, 65) == 24
assert segment_count(130, 65) == 2
assert segment_count(130.0000001, 65) == 2
assert segment_count(5.0, 65) == 1
assert segment_count(0, 65) == 0

print("core tests: OK")

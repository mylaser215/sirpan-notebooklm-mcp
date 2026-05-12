# v4 결함 검증용 markdown 테스트 파일

이 파일은 `_register_file_source` payload 구조 픽스 후 NLM이 markdown을 정상 파싱하는지 검증용입니다.

## 표 검증

| 컬럼A | 컬럼B | 컬럼C |
|-------|-------|-------|
| 셀1 | 셀2 | 셀3 |
| 셀4 | **굵은셀5** | `inline_code` |

## 헤딩 검증

### H3 헤딩

본문 텍스트 — *italic* 과 **bold** 와 `code`.

## 코드 블록 검증

```python
def hello():
    print("hello world")
    return 42
```

## 불릿 리스트 검증

- 첫 번째
- 두 번째
  - 중첩 1
  - 중첩 2
- 세 번째

## 결론

이 모든 요소가 NLM 웹에서 살아있으면 가설 H 확정. 깨지면 다른 가설 재탐색.

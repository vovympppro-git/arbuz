"""Пример простых тестов"""

def test_addition():
    """Проверяем сложение"""
    assert 1 + 1 == 2

def test_subtraction():
    """Проверяем вычитание"""
    assert 5 - 3 == 2

def test_string_concatenation():
    """Проверяем конкатенацию строк"""
    assert "Hello" + " " + "World" == "Hello World"

def test_boolean():
    """Проверяем булевы значения"""
    assert True is True

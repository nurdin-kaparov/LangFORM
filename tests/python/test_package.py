def test_package_import():
    import langform
    assert langform.__version__ == "0.3.0"
    assert not hasattr(langform, "MemoryItem")

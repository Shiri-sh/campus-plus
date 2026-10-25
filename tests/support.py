from datetime import date


def freeze_module_date(monkeypatch, module, day):
    class FrozenDate(date):
        @classmethod
        def today(cls):
            return day

    monkeypatch.setattr(module, "date", FrozenDate)

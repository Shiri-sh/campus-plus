from types import SimpleNamespace

from scripts.seed_embeddings import material_document, select_seed_materials


def _material(material_id, course_id, material_type, file_name="file.pdf"):
    return SimpleNamespace(
        id=material_id,
        course_id=course_id,
        material_type=material_type,
        file_name=file_name,
        academic_year=2024,
        course=SimpleNamespace(name="פיזיקה"),
    )


def test_material_document_joins_metadata():
    material = _material(1, 1, "exams", file_name="מועד א.pdf")

    document = material_document(material)

    assert "מועד א.pdf" in document
    assert "פיזיקה" in document
    assert "exams" in document
    assert 'תשפ"ד' in document


def _exam_rows():
    return [
        _material(0, 1, "exams"),
        _material(1, 1, "exams"),
        _material(2, 1, "exams"),
        _material(3, 1, "exams"),
        _material(4, 1, "exams"),
        _material(5, 1, "exams"),
        _material(6, 1, "exams"),
        _material(7, 1, "exams"),
        _material(8, 1, "exams"),
        _material(9, 1, "exams"),
        _material(10, 1, "exams"),
        _material(11, 1, "exams"),
    ]


def test_select_seed_materials_caps_at_the_limit():
    selected = select_seed_materials(_exam_rows(), limit=8)

    assert [item.id for item in selected] == [0, 1, 2, 3, 4, 5, 6, 7]


def test_select_seed_materials_spreads_across_course_and_type():
    materials = [
        _material(1, 1, "exams"),
        _material(2, 1, "exams"),
        _material(3, 1, "summaries"),
        _material(4, 2, "exams"),
    ]

    selected = select_seed_materials(materials, limit=3)

    assert [item.id for item in selected] == [1, 3, 4]

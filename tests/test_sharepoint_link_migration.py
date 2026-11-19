from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, CVDocument, Personnel
from sharepoint_link_migration import (
    import_sharepoint_mapping,
    load_sharepoint_mapping,
    normalize_match_value,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def mapping_row(name, staff_id, filename, url):
    return [
        name,
        staff_id,
        "Executive",
        "Found",
        filename,
        filename.rsplit(".", 1)[-1].upper(),
        "",
        "",
        "",
        url,
        "46300",
        "Exact ECMS path match",
        "Updated to ecm_ups_coe SharePoint link",
    ]


def test_mapping_loader_reads_headerless_tab_delimited_excel_copy():
    row = mapping_row(
        "Example Person",
        "",
        "Example CV.pdf",
        "https://petronas.sharepoint.com/sites/ecm_ups_coe/PE-RE/Example.pdf",
    )
    payload = "\t".join(row).encode("utf-8")
    frame = load_sharepoint_mapping("mapping.txt", payload)

    assert len(frame) == 1
    assert frame.loc[0, "Name"] == "Example Person"
    assert frame.loc[0, "CV File Name"] == "Example CV.pdf"
    assert frame.loc[0, "File Type"] == "PDF"
    assert frame.loc[0, "SharePoint URL"].endswith("Example.pdf")
    assert frame.loc[0, "Modified Date Parsed"] is not None


def test_import_updates_existing_document_by_exact_person_and_filename():
    session = make_session()
    person = Personnel(
        staff_id="10001",
        name="Abdul Hakim bin Ameludin",
        is_deleted=False,
    )
    session.add(person)
    session.flush()
    document = CVDocument(
        personnel_id=person.id,
        cv_file_name="CV_Abdul Hakim bin Ameludin.pdf",
        file_type="PDF",
        sharepoint_url="https://petronas.sharepoint.com/sites/old/old.pdf",
        is_deleted=False,
    )
    session.add(document)
    session.flush()

    frame = load_sharepoint_mapping(
        "mapping.tsv",
        ("\t".join(mapping_row(
            "Abdul Hakim bin Ameludin",
            "10001",
            "CV_Abdul Hakim bin Ameludin.pdf",
            "https://petronas.sharepoint.com/sites/ecm_ups_coe/PE-RE/new.pdf",
        ))).encode("utf-8"),
    )
    result = import_sharepoint_mapping(session, frame)

    assert result["updated"] == 1
    assert result["added"] == 0
    assert result["unmatched"] == 0
    assert document.sharepoint_url.endswith("/new.pdf")
    assert document.match_method == "Staff ID + exact normalized personnel name"
    session.close()


def test_import_creates_supporting_document_when_filename_is_not_registered():
    session = make_session()
    person = Personnel(
        staff_id="10002",
        name="A Hakim Basri",
        is_deleted=False,
    )
    session.add(person)
    session.flush()
    frame = load_sharepoint_mapping(
        "mapping.txt",
        ("\t".join(mapping_row(
            "A Hakim Basri",
            "",
            "Attachment 1 SMA Record.pdf",
            "https://petronas.sharepoint.com/sites/ecm_ups_coe/PE-RE/sma.pdf",
        ))).encode("utf-8"),
    )

    result = import_sharepoint_mapping(session, frame)
    session.flush()
    documents = session.query(CVDocument).filter_by(personnel_id=person.id).all()

    assert result["added"] == 1
    assert len(documents) == 1
    assert documents[0].cv_file_name == "Attachment 1 SMA Record.pdf"
    assert documents[0].sharepoint_url.endswith("/sma.pdf")
    session.close()


def test_import_does_not_use_partial_name_matching():
    session = make_session()
    session.add(Personnel(
        staff_id="10003",
        name="Abdul Hakim bin Ameludin",
        is_deleted=False,
    ))
    session.flush()
    frame = load_sharepoint_mapping(
        "mapping.txt",
        ("\t".join(mapping_row(
            "Abdul Hakim",
            "",
            "CV.pdf",
            "https://petronas.sharepoint.com/sites/ecm_ups_coe/PE-RE/cv.pdf",
        ))).encode("utf-8"),
    )

    result = import_sharepoint_mapping(session, frame)

    assert result["unmatched"] == 1
    assert result["added"] == 0
    session.close()


def test_normalization_is_case_and_punctuation_insensitive_but_exact():
    assert normalize_match_value("A. Hakim-Basri") == normalize_match_value("a hakim basri")
    assert normalize_match_value("Abdul Hakim") != normalize_match_value("Abdul Hakim Basri")

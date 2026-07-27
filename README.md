# Complete low-carbon construction Streamlit dashboard

This package uses the same source data prepared for the Tableau teaching model:

- four construction-site presets;
- four plant and temporary-power strategies;
- five emission factors;
- six plant specifications;
- operational and expanded energy-carbon boundaries;
- all 16 context–strategy combinations;
- source and data-quality notes;
- the original Tableau Excel workbook.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

The app normally opens at:

```text
http://localhost:8501
```

## Publish free through Streamlit Community Cloud

1. Create a GitHub repository.
2. Upload every file and folder in this package.
3. Keep `app.py` and `requirements.txt` in the repository root.
4. Sign in to Streamlit Community Cloud.
5. Create a new app.
6. Select the repository and `main` branch.
7. Set the main file path to `app.py`.
8. Deploy.
9. Test the public link on a mobile phone.
10. Send the public URL to ChatGPT for the QR code and final interview slide.

## Public-data statement

The dashboard contains public and fictional teaching data only. It contains no confidential project,
employer or apprentice information.

## Important modelling limitation

This is an educational comparison, not a certified whole-life carbon assessment. Machine and battery
manufacture and end-of-life impacts are outside the current model.

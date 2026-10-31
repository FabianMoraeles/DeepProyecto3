import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Instala requirements.txt para pruebas UI')
class InterfaceTests(unittest.TestCase):
    @patch('app.pipeline.complete', side_effect=AssertionError('La prueba guiada no debe llamar a una IA'))
    def test_navigation_and_guided_query(self, complete_mock):
        # Inicialización de bibliotecas fuera del watchdog de interacciones UI.
        # El tiempo de arranque frío se mide por separado, no como latencia del producto.
        import pandas
        import plotly.express
        from datoclaro.io import ROOT
        if (ROOT/'data/databases/california_schools/california_schools.sqlite').exists():
            from app.runtime import db_path
            db_path('california_schools')
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'), default_timeout=30).run()
        self.assertEqual(len(app.exception),0)
        next(widget for widget in app.selectbox if widget.label == 'Motor de análisis').set_value('Demostración guiada').run()
        self.assertIn('Escuelas por condado',app.button[0].label)
        app.button[0].click().run()
        self.assertIn('condados',app.text_area[0].value)
        # GUI smoke de la consulta depende de las bases locales, no de CI.
        if (ROOT/'data/databases/california_schools/california_schools.sqlite').exists():
            app.button[3].click().run(timeout=30)
            self.assertEqual(len(app.exception),0)
            output=app.session_state['result']['output']
            self.assertEqual(output['status'],'ok',repr(output))
        for page in ['Catálogo de datos','Historial','Evaluación','Acerca del proyecto']:
            app.radio[0].set_value(page).run()
            self.assertEqual(len(app.exception),0, page)
        complete_mock.assert_not_called()


if __name__ == '__main__': unittest.main()

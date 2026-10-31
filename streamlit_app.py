if __name__ == '__main__':
    # Windows/macOS spawn vuelven a cargar este archivo como __mp_main__.
    # Los procesos SQL no deben importar ni ejecutar la interfaz.
    from app.streamlit_app import main
    main()

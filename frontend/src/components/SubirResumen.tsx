import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import {
  mensajeDeError,
  subirResumen,
  type ResultadoImportacion,
} from "../api/client";

export default function SubirResumen() {
  const inputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const [resultado, setResultado] = useState<ResultadoImportacion | null>(null);
  const [encima, setEncima] = useState(false);

  const mutacion = useMutation({
    mutationFn: subirResumen,
    onSuccess: (data) => {
      setResultado(data);
      queryClient.invalidateQueries({ queryKey: ["transferencias"] });
    },
  });

  const mensajeError = mutacion.error
    ? mensajeDeError(mutacion.error, "No se pudo procesar el archivo")
    : null;

  const enviar = (archivo: File | undefined) => {
    if (!archivo) return;
    setResultado(null);
    mutacion.mutate(archivo);
  };

  return (
    <Card>
      <CardContent>
        <Stack
          direction="row"
          spacing={1}
          alignItems="baseline"
          sx={{ mb: 0.5 }}
        >
          <Typography variant="h6">Subir resumen bancario</Typography>
          <Typography variant="caption" color="text.secondary">
            paso 1
          </Typography>
        </Stack>
        <Typography variant="body2" color="text.secondary">
          Excel, CSV o PDF exportado de Santander o Macro. Se detectan las
          transferencias recibidas (CUIT del emisor, importe y fecha) y se
          omiten las que ya habías importado.
        </Typography>

        <Box
          onDragOver={(e) => {
            e.preventDefault();
            setEncima(true);
          }}
          onDragLeave={() => setEncima(false)}
          onDrop={(e) => {
            e.preventDefault();
            setEncima(false);
            enviar(e.dataTransfer.files?.[0]);
          }}
          onClick={() => !mutacion.isPending && inputRef.current?.click()}
          sx={{
            mt: 2,
            px: 2,
            py: 3,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 1.25,
            textAlign: "center",
            cursor: mutacion.isPending ? "default" : "pointer",
            borderRadius: 2,
            border: (t) =>
              `1px dashed ${encima ? t.palette.primary.main : t.palette.divider}`,
            bgcolor: (t) =>
              encima ? "action.hover" : t.palette.background.default,
            transition: "border-color .15s, background-color .15s",
          }}
        >
          <UploadFileIcon color={encima ? "primary" : "disabled"} />
          <Typography variant="body2" color="text.secondary">
            Arrastrá el archivo acá o
          </Typography>
          <Button
            variant="contained"
            size="small"
            disabled={mutacion.isPending}
          >
            {mutacion.isPending ? "Procesando…" : "Elegir archivo"}
          </Button>
          <Typography variant="caption" color="text.secondary">
            .xlsx · .xls · .csv · .pdf — hasta 10 MB
          </Typography>
          <input
            ref={inputRef}
            type="file"
            hidden
            accept=".xlsx,.xlsm,.xls,.csv,.pdf"
            onChange={(e) => {
              enviar(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </Box>
        {mutacion.isPending && (
          <LinearProgress sx={{ mt: 1.5, borderRadius: 1 }} />
        )}

        {mensajeError && (
          <Alert
            severity="error"
            sx={{ mt: 2 }}
            onClose={() => mutacion.reset()}
            action={
              <Button
                color="inherit"
                size="small"
                onClick={() => inputRef.current?.click()}
              >
                Reintentar
              </Button>
            }
          >
            {mensajeError}
          </Alert>
        )}
        {resultado && (
          <Alert
            severity={resultado.nuevas > 0 ? "success" : "info"}
            sx={{ mt: 2 }}
          >
            {`${resultado.lote.nombre_archivo} (${resultado.lote.banco}): ${resultado.nuevas} transferencias nuevas, ${resultado.duplicadas} duplicadas omitidas, ${resultado.sin_cuit} sin CUIT detectado.`}
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}

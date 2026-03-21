import { useParams } from 'react-router-dom';

export function JobPage(): React.JSX.Element {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
        <h1 className="text-2xl font-semibold text-gray-800 mb-2">
          Job {id}
        </h1>
        <p className="text-gray-500">Coming soon</p>
      </div>
    </div>
  );
}
